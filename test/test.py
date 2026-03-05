from openai import OpenAI
import time

client_base = OpenAI(base_url='http://localhost:8000/v1', api_key='not-needed', timeout=120)
client_dbg = OpenAI(base_url='http://localhost:8001/v1', api_key='not-needed', timeout=120)

BUGGY = '''module adder_8bit(
    input [7:0] a, b,
    input cin,
    output [7:0] sum,
    output cout
);
    // Bug: result is not declared
    assign result = a + b + cin;
    assign sum = result[7:0];
    assign cout = result[8];
endmodule
'''

ERROR_LOG = '''%Error: adder_8bit.v:8: Signal result not found
%Error: adder_8bit.v:9: Signal result not found
%Error: adder_8bit.v:10: Signal result not found
%Error: Exiting due to 3 error(s)'''

msgs = [
    {'role': 'system', 'content': 'You are a Verilog syntax debugging expert. Fix the TOPMOST error. Return ONLY the complete fixed Verilog code.'},
    {'role': 'user', 'content': f'## Module: adder_8bit\n### Current Verilog Code\n```verilog\n{BUGGY}\n```\n### Topmost Verilator Error\n{ERROR_LOG.split(chr(10))[0]}\n### Full Log\n{ERROR_LOG}\nFix the topmost error and return the complete corrected Verilog code.'}
]

print('='*60)
print('  BASE MODEL (qwen-base, GPU 0)')
print('='*60)
t0 = time.time()
r = client_base.chat.completions.create(model='qwen-base', messages=msgs, temperature=0.1, max_tokens=2048)
print(f'Time: {time.time()-t0:.1f}s | Tokens: {r.usage.prompt_tokens}->{r.usage.completion_tokens}')
print(r.choices[0].message.content)

print()
print('='*60)
print('  DEBUGGER LORA (debugger, GPU 1)')
print('='*60)
t0 = time.time()
r = client_dbg.chat.completions.create(model='debugger', messages=msgs, temperature=0.1, max_tokens=2048)
print(f'Time: {time.time()-t0:.1f}s | Tokens: {r.usage.prompt_tokens}->{r.usage.completion_tokens}')
print(r.choices[0].message.content)

