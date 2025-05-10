# OpenAI compatible API 
vlm4ocr --input_path /home/daviden1013/David_projects/vlm4ocr/examples/synthesized_data/GPT-4o_synthesized_note_1.pdf \
        --output_mode markdown \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --verbose 

# OpenAI compatible API (batch processing)
vlm4ocr --input_path /home/daviden1013/David_projects/vlm4ocr/examples/synthesized_data/ \
        --output_mode markdown \
        --vlm_engine openai_compatible \
        --model Qwen/Qwen2.5-VL-7B-Instruct \
        --api_key EMPTY \
        --base_url http://localhost:8000/v1 \
        --concurrent \
        --concurrent_batch_size 4 \

# OpenAI API
export OPENAI_API_KEY=<api key>
vlm4ocr --input_path /home/daviden1013/David_projects/vlm4ocr/examples/synthesized_data/GPT-4o_synthesized_note_1.pdf \
        --output_mode HTML \
        --vlm_engine openai \
        --model gpt-4o-mini \
        --concurrent \
        --concurrent_batch_size 4 \