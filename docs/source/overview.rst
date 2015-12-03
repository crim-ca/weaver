.. _overview:

********
Overview
********

.. contents::
    :local:
    :depth: 2


The following image gives an overview of the Twitcher components.

.. image:: _images/twitcher-overview.png

Twitcher consists of the following main parts:

OWS Security
   A wsgi middleware (actually currently it is a `Pyramid tween <http://docs.pylonsproject.org/projects/pyramid/en/latest/glossary.html#term-tween>`_) which puts a simple token based security layer on top of a wsgi application. The access tokens are stored currently store in a MongoDB.
OWS Proxy
   A wsgi application which acts as a proxy for registred OWS services. Currently it only supports WPS services.
WPS
   A wsgi application which provides a configurable Web Processing Service (WPS). Currently it uses PyWPS.
XML-RPC Interface
   An XML-RPC service which is used to control the token generation and OWS service registration. The interface is accessed using Basic Authentication. It should be used by an administrator and administrative web portals.


The OWS security middleware protects OWS services with a simple string based token mechanism.  
A WPS client needs to provide a string token to access the internal WPS or a registered OWS service. 
A token is generated via the XML-RPC interface. This interface is supposed to be used by an external administration client which has user authentication and generates an access token on behalf of the user. 

So, twitcher is meant to be integrated in existing processing infrastructures with OGC/OWS services and portals. You can use twitcher as a standalone service but currently only for development and demo purposes.
