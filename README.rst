===========
pywps-proxy
===========

pywps-proxy is a security proxy for Web Processing Services (WPS). The execution of a WPS process is blocked by the proxy. The proxy service provides access tokens (uuid) which needs to be used to run a WPS process. The access tokens are valid only for a short period of time.

pywps-proxy is a prototype implemented in Python with the Pyramid web framework.

pywps-proxy comes in two flavours:

* *A security proxy for Web Processing Services implemented in Python*
* *A security proxy for PyWPS with WSGI application layers*

pywps-proxy is a working title. It's not a *bird* yet. It may become a candidate for the `GeoPython <http://geopython.github.io/>`_ project. 


Links
=====

OWS Proxies:

* `owsproxy by mapbender <https://github.com/mapbender/owsproxy3>`_  
* http://www.mapbender.org/OWS_Security_Proxy
* https://github.com/camptocamp/secureOWS
* https://github.com/elemoine/papyrus_ogcproxy
* http://proxy4ows.org/
* http://www.slideshare.net/jachym/proxy4ows
* http://wiki.deegree.org/deegreeWiki/deegree3/SecurityRequirements

Other Proxies:

* http://mapproxy.org/

Security Filters:

* `FOSS4G Talk <http://www.slideshare.net/JorgeMendesdeJesus/pywps-a-tutorial-for-beginners-and-developers>`_ on using `mod_python <http://www.modpython.org/>`_ with security filter for PyWPS.  

Pyramid:

* https://github.com/elemoine/papyrus
* https://github.com/elemoine/papyrus_mapproxy
* http://pythonpaste.org/modules/proxy.html

Macaroons Tokens (simple security tokens for distributed systems):

* https://github.com/rescrv/libmacaroons
* http://hackingdistributed.com/2014/05/16/macaroons-are-better-than-cookies/
* https://github.com/shirkey/macaroons-kopdar/
