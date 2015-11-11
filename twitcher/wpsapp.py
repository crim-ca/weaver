"""
PyWPS wsgi script

    SetHandler python-program
    PythonHandler wps
    PythonDebug On
    PythonPath "sys.path+['/usr/local/pywps-VERSION/']"
    PythonAutoReload On

.. moduleauthor: Jachym Cepicky jachym bnhelp cz
"""

# Author:   Jachym Cepicky
#           http://les-ejk.cz
# License:
#
# Web Processing Service implementation
# Copyright (C) 2006 Jachym Cepicky
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import pywps
from pywps.Exceptions import *

def app(environ, start_response):

    status = '200 OK'
    response_headers = [('Content-type','text/xml')]
    start_response(status, response_headers)

    inputQuery = None
    if "REQUEST_METHOD" in environ and environ["REQUEST_METHOD"] == "GET":
        inputQuery = environ["QUERY_STRING"]
    elif "wsgi.input" in environ:
        inputQuery = environ['wsgi.input']

    if not inputQuery:
        err =  NoApplicableCode("No query string found.")
        return [err.getResponse()]


    # create the WPS object
    try:
        wps = pywps.Pywps(environ["REQUEST_METHOD"])
        if wps.parseRequest(inputQuery):
            pywps.debug(wps.inputs)
            wps.performRequest()
            return wps.response
    except WPSException,e:
        return [e]
    except Exception, e:
        return [e]


