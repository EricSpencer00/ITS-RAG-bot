"""Benchmark LLM models for speed."""
import requests, time, json

models = ['gemma:2b', 'llama3.1:8b']
msg = [{'role': 'user', 'content': 'My VPN wont connect. Quick help.'}]

for model in models:
    payload = {'model': model, 'messages': msg, 'stream': True, 'options': {'temperature': 0.1, 'num_predict': 80}}
    t = time.time()
    first_token_time = None
    full_text = ''
    try:
        with requests.post('http://localhost:11434/api/chat', json=payload, stream=True, timeout=60) as r:
            for line in r.iter_lines():
                if line:
                    d = json.loads(line)
                    tok = d.get('message', {}).get('content', '')
                    if tok and first_token_time is None:
                        first_token_time = time.time() - t
                    full_text += tok
                    if d.get('done'):
                        break
        total_time = time.time() - t
        words = len(full_text.split())
        print(f'{model}: TTFB={first_token_time:.2f}s  total={total_time:.2f}s  words={words}')
        print(f'  Response: {full_text[:150]}')
        print()
    except Exception as e:
        print(f'{model}: ERROR - {e}')
