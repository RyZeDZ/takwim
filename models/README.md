# Models

The import screen can use a small local language model to recognise column headers the
built-in dictionary doesn't know (see `ai/column_mapper.py`). It runs on the CPU, offline.

Model: **Qwen2.5-1.5B-Instruct**, 4-bit GGUF (about 1 GB), Apache 2.0 licence.

```bash
cd models
curl -L -o qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
pip install llama-cpp-python   # in the backend's virtual environment
```

Then set `COLUMN_MAPPER_MODULE=ai.column_mapper` in `backend/.env`. Without the model, imports
still work with the dictionary alone.

On a server started with `python backend/serve.py`, the model is downloaded automatically on
the first start when `COLUMN_MAPPER_MODULE` is set and the file is missing.
