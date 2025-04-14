# Genterated automatically by /run.ipynb
from pydantic_xml import BaseXmlModel, attr, element
from pydantic import Field
from typing import Optional, Union, List

class IDModel(BaseXmlModel):
    id: str = attr()
class IO(IDModel):
    description: Optional[str] = None
    width_description: Optional[str] = attr(default=None)
class Ports(BaseXmlModel, tag="ports"):
    input: List[IO] = element()
    output: List[IO] = element()
class Module(IDModel, tag='module'):
    description: str = element(default=None)
    ports: Optional[Ports] = element(default=None)
    implementation: str = element()
    task: str = element(default="Give me the complete Verilog code.")
