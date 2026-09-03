from typing import List
import os
import yaml
import asyncio
import argparse
import logging
import json
from glob import glob
from vlm4ocr import VLLMVLMEngine, AzureOpenAIVLMEngine, OCREngine
from tqdm.asyncio import tqdm


async def run_pipeline(ocr_engine: OCREngine, file_paths: List[str], output_dir: str, messages_log_dir: str, 
                       run_name: str, concurrent_batch_size: int, max_file_load: int):
    """
    Runs the OCR processing logic using a pre-configured engine.
    """
    pbar = tqdm(total=len(file_paths), desc="Processing files", unit="file")

    # Process files concurrently
    async for result in ocr_engine.concurrent_ocr(
            file_paths,
            concurrent_batch_size=concurrent_batch_size,
            max_file_load=max_file_load
    ):
        
        base_filename = os.path.basename(result.filename)
        filename_no_ext = os.path.splitext(base_filename)[0]
        
        if result.status == "success":
            logging.info(f"Successfully processed {base_filename}")
            for i, page in enumerate(result.pages):
                text_output = page['text']
                with open(os.path.join(output_dir, run_name, f"{filename_no_ext}_page {i}.md"), 'w') as f:
                    f.write(text_output)
        else:
            logging.error(f"Failed to process {base_filename}.")
        
        with open(os.path.join(messages_log_dir, run_name, f"{filename_no_ext}.json"), 'w') as f:
            json.dump(result.get_messages_log(), f, indent=4)

        pbar.update(1)

    pbar.close()


def main():
    parser = argparse.ArgumentParser(description="Run the vlm4ocr pipeline.")
    parser.add_argument("-c", "--config", type=str, default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

    with open(args.config, 'r') as f:
        config = yaml.safe_load(f)

    vlm_config = config['vlm_engine']
    ocr_config = config['ocr_engine']
    
    # Init VLM
    if vlm_config['base_url'] == "http://localhost:8000/v1":
        vlm_engine = VLLMVLMEngine(
            model=vlm_config['model'],
            config=eval(vlm_config["config"])
        )
    else:
        vlm_engine = AzureOpenAIVLMEngine(
            model=vlm_config['model'],
            api_version=vlm_config["api_version"],
            azure_endpoint=vlm_config["azure_endpoint"],
            config=eval(vlm_config["config"])
        )

    # Init OCR Prompt
    try:
        with open(ocr_config['user_prompt_path'], 'r') as f:
            user_prompt = f.read()
    except (FileNotFoundError, KeyError) as e:
        logging.error(f"Error loading prompt: {e}")
        return

    ocr_engine = OCREngine(
        vlm_engine,
        output_mode=config['ocr_engine']['output_mode'],
        user_prompt=user_prompt,
        # Required for PDF input; vlm4ocr ships no PDF library. See config.yaml.
        pdf_backend=config['ocr_engine'].get('pdf_backend'),
        pdf_dpi=config['ocr_engine'].get('pdf_dpi', 200)
    )

    # Ensure the output directory exists
    os.makedirs(os.path.join(config['output_directory'], config['run_name']), exist_ok=True)
    os.makedirs(os.path.join(config['messages_log_dir'], config['run_name']), exist_ok=True)

    # Get a list of supported files
    supported_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tif', '.tiff']
    file_paths = []
    for ext in supported_extensions:
        file_paths.extend(glob(os.path.join(config['input_directory'], f"**/*{ext}"), recursive=True))

    file_paths = sorted(list(set(file_paths)))

    if not file_paths:
        logging.warning(f"No supported files found in {config['input_directory']}")
        return

    logging.info(f"Found {len(file_paths)} files to process.")

    # Run the OCR pipeline
    asyncio.run(run_pipeline(
        ocr_engine=ocr_engine,
        file_paths=file_paths,
        output_dir=config['output_directory'],
        messages_log_dir=config["messages_log_dir"],
        run_name=config['run_name'],
        concurrent_batch_size=ocr_config['concurrent_batch_size'],
        max_file_load=ocr_config['max_file_load']
    ))

if __name__ == "__main__":
    main()