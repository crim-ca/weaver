.. _overview:

********
Overview
********

.. contents::
    :local:
    :depth: 2


Twitcher Components
===================

Twitcher has the following components:

OWS Security
   A wsgi middleware (actually currently it is a `Pyramid tween <http://docs.pylonsproject.org/projects/pyramid/en/latest/glossary.html#term-tween>`_) which puts a simple token based security layer on top of a wsgi application.
OWS Proxy
   A wsgi application which acts as a proxy for registred OWS services. Currently it only supports WPS services.
WPS
   A wsgi application which provides a configurable Web Processing Service (WPS). Currently it uses PyWPS.
XML-RPC Interface
   An XML-RPC service which is used to control the token generation and OWS service registration. The interface is accessed using Basic Authentication. It should be used by an administrator and administrative web portals.

