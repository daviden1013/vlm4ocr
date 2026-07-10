"""
routed_concurrent_pipeline.py

Example: routed OCR for heterogeneous documents (e.g. cognitive assessment forms,
where a single PDF/TIFF interleaves several form types). Each page is classified,
then extracted with the schema for its type.

RoutedOCRPipeline is intentionally NOT part of vlm4ocr -- it is project-specific
policy. It is a thin subclass of the shipped vlm4ocr.IndependentPagePipeline whose
process_page classifies a page and routes it to a per-type extractor engine. All
orchestration (loading, concurrency, ordering, assembly) is inherited; this file
only supplies the routing logic and I/O.
"""
from typing import Callable, Dict
import os
import json
import yaml
import asyncio
import logging
import argparse
from glob import glob

from PIL import Image
from tqdm.asyncio import tqdm

from vlm4ocr import (VLLMVLMEngine, AzureOpenAIVLMEngine, OCREngine, OCRPage,
                     IndependentPagePipeline)
from vlm4ocr.vlm_engines import MessagesLogger

SUPPORTED_EXTS = ['.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff']


def parse_page_type(classifier_text: str) -> str:
    """Read "page_type" from a JSON-mode classifier output (a JSON array string)."""
    try:
        data = json.loads(classifier_text)
    except (json.JSONDecodeError, TypeError):
        return "unknown"
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return "unknown"
    return data.get("page_type") or "unknown"


class RoutedOCRPipeline(IndependentPagePipeline):
    """Classify each page, then route it to the matching extractor OCREngine."""
    def __init__(self, classifier: OCREngine, routes: Dict[str, OCREngine], default: OCREngine, *,
                 route_key: Callable[[str], str] = parse_page_type, **kwargs):
        self.classifier = classifier
        self.routes = routes
        self.default = default
        self.route_key = route_key
        super().__init__(self._classify_and_extract, output_mode="JSON", **kwargs)

    async def _classify_and_extract(self, image: Image.Image, *, messages_logger: MessagesLogger = None) -> OCRPage:
        # Sees only its own image -> independent. Both calls share the logger for one audit trail.
        classification = await self.classifier.ocr_image_async(image, messages_logger=messages_logger)
        page_type = self.route_key(classification.text)
        extractor = self.routes.get(page_type, self.default)
        page = await extractor.ocr_image_async(image, messages_logger=messages_logger)
        page.metadata["page_type"] = page_type
        return page


async def run_pipeline(pipeline: RoutedOCRPipeline, file_paths, output_dir, messages_log_dir,
                       run_name, concurrent_batch_size, max_file_load):
    pbar = tqdm(total=len(file_paths), desc="Processing files", unit="file")
    async for result in pipeline.concurrent_ocr(file_paths, concurrent_batch_size=concurrent_batch_size,
                                                max_file_load=max_file_load):
        stem = os.path.splitext(os.path.basename(result.filename))[0]
        if result.status == "success":
            logging.info(f"Successfully processed {result.filename} ({len(result)} pages)")
            for i, page in enumerate(result.pages):
                page_type = page['metadata'].get('page_type', 'unknown')
                with open(os.path.join(output_dir, run_name, f"{stem}_page{i}_{page_type}.json"), 'w') as f:
                    f.write(page['text'])
        else:
            logging.error(f"Failed to process {result.filename}")
        with open(os.path.join(messages_log_dir, run_name, f"{stem}.json"), 'w') as f:
            json.dump(result.get_messages_log(), f, indent=4)
        pbar.update(1)
    pbar.close()


def build_vlm_engine(vlm_config: dict):
    if vlm_config['base_url'] == "http://localhost:8000/v1":
        return VLLMVLMEngine(model=vlm_config['model'], config=eval(vlm_config["config"]))
    return AzureOpenAIVLMEngine(
        model=vlm_config['model'], api_version=vlm_config["api_version"],
        azure_endpoint=vlm_config["azure_endpoint"], config=eval(vlm_config["config"]))


def load_prompt(path: str) -> str:
    with open(path, 'r') as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="Run the routed vlm4ocr pipeline.")
    parser.add_argument("-c", "--config", type=str, default="routed_config.yaml")
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    vlm_engine = build_vlm_engine(config['vlm_engine'])

    # Each OCREngine is an atom: one prompt, one task. The pipeline composes them.
    pipeline = RoutedOCRPipeline(
        classifier=OCREngine(vlm_engine, output_mode="JSON",
                             user_prompt=load_prompt(config['classifier']['user_prompt_path'])),
        routes={pt: OCREngine(vlm_engine, output_mode="JSON",
                             user_prompt=load_prompt(cfg['user_prompt_path']))
                for pt, cfg in config['routes'].items()},
        default=OCREngine(vlm_engine, output_mode="JSON",
                         user_prompt=load_prompt(config['default_route']['user_prompt_path'])),
    )

    os.makedirs(os.path.join(config['output_directory'], config['run_name']), exist_ok=True)
    os.makedirs(os.path.join(config['messages_log_directory'], config['run_name']), exist_ok=True)

    file_paths = []
    for ext in SUPPORTED_EXTS:
        file_paths.extend(glob(os.path.join(config['input_directory'], f"**/*{ext}"), recursive=True))
    file_paths = sorted(set(file_paths))
    if not file_paths:
        logging.warning(f"No supported files found in {config['input_directory']}")
        return
    logging.info(f"Found {len(file_paths)} files to process.")

    pipe = config['pipeline']
    asyncio.run(run_pipeline(
        pipeline=pipeline, file_paths=file_paths,
        output_dir=config['output_directory'], messages_log_dir=config['messages_log_directory'],
        run_name=config['run_name'],
        concurrent_batch_size=pipe['concurrent_batch_size'], max_file_load=pipe['max_file_load']))


if __name__ == "__main__":
    main()
