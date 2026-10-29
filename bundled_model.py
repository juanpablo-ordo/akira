"""Pinned Google Gemma 4 E2B IT text model, converted by Unsloth (Apache-2.0)."""
MODEL_NAME='gemma-4-E2B-it-Q4_K_M.gguf'
MODEL_SHA='740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8'
MODEL_SIZE=3106738272
MODEL_URL='https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/0314792d7f1f7e229411f620751375812bb9faf2/'+MODEL_NAME
MODEL_PATH='local_ai/models/'+MODEL_NAME
LEGACY_MODEL_NAME='Qwen3-4B-Q4_K_M.gguf'
LEGACY_MODEL_PATH='local_ai/models/'+LEGACY_MODEL_NAME


def conversation_sampling(model,reference=False):
    if 'gemma-4-' in str(model).lower():
        return {'temperature':0 if reference else 1.0,'top_p':.95,'top_k':64,'min_p':0,'seed':42}
    return {'temperature':0}
