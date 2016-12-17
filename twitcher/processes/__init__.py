from .wps_hello import Hello
from .wps_showenv import ShowEnv
from .wps_ncdump import NCDump

processes = [
    Hello(),
    ShowEnv(),
    NCDump(),
]
