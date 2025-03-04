import re

def md_code_extract(text:str):
    found = re.search(r'^```(\w*)\n(?P<code>(.|\n)*)```', text, re.MULTILINE)
    return found.groupdict()['code']