"""
Store adapters to persist and retrieve data during the twitcher process or
for later use. For example an access token storage and a service registry.

This module provides base classes that can be extended to implement your own
solution specific to your needs.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.io/en/latest/>`_.
"""


class AccessTokenStore(object):

    def save_token(self, access_token):
        """
        Stores an access token with additional data.
        """
        raise NotImplementedError

    def delete_token(self, token):
        """
        Deletes an access token from the store using its token string to identify it.
        This invalidates both the access token and the token.

        :param token: A string containing the token.
        :return: None.
        """
        raise NotImplementedError

    def fetch_by_token(self, token):
        """
        Fetches an access token from the store using its token string to
        identify it.

        :param token: A string containing the token.
        :return: An instance of :class:`twitcher.datatype.AccessToken`.
        """
        raise NotImplementedError

    def clear_tokens(self):
        """
        Removes all tokens from database.
        """
        raise NotImplementedError


class ServiceStore(object):
    """
    Storage for OWS services.
    """

    def save_service(self, service, overwrite=True, request=None):
        """
        Stores an OWS service in storage.

        :param service: An instance of :class:`twitcher.datatype.Service`.
        """
        raise NotImplementedError

    def delete_service(self, name, request=None):
        """
        Removes service from database.
        """
        raise NotImplementedError

    def list_services(self, request=None):
        """
        Lists all services in database.
        """
        raise NotImplementedError

    def fetch_by_name(self, name, request=None):
        """
        Get service for given ``name`` from storage.

        :param name: A string containing the service name.
        :return: An instance of :class:`twitcher.datatype.Service`.
        """
        raise NotImplementedError

    def fetch_by_url(self, url, request=None):
        """
        Get service for given ``url`` from storage.

        :return: An instance of :class:`twitcher.datatype.Service`.
        """
        raise NotImplementedError

    def clear_services(self, request=None):
        """
        Removes all OWS services from storage.
        """
        raise NotImplementedError


class ProcessStore(object):
    """
    Storage for local WPS processes.
    """

    def save_process(self, process, overwrite=True, request=None):
        """
        Stores a WPS process in storage.

        :param process: An instance of :class:`twitcher.datatype.Process`.
        """
        raise NotImplementedError

    def delete_process(self, process_id, request=None):
        """
        Removes process from database.
        """
        raise NotImplementedError

    def list_processes(self, request=None):
        """
        Lists all processes in database.
        """
        raise NotImplementedError

    def fetch_by_id(self, process_id, request=None):
        """
        Get process for given ``name`` from storage.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        raise NotImplementedError


class JobStore(object):
    """
    Storage for job tracking.
    """

    def save_job(self, task_id, process, service=None, is_workflow=False, user_id=None, async=True):
        """
        Stores a job in storage.
        """
        raise NotImplementedError

    def update_job(self, job, attributes):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        :param attributes: dictionary of field:value to update.
        """
        raise NotImplementedError

    def delete_job(self, name, request=None):
        """
        Removes job from database.
        """
        raise NotImplementedError

    def fetch_by_id(self, job_id, request=None):
        """
        Get job for given ``job_id`` from storage.
        """
        raise NotImplementedError

    def list_jobs(self, request=None):
        """
        Lists all jobs in database.
        """
        raise NotImplementedError

    def find_jobs(self, request, page=0, limit=10, process=None, service=None,
                  tag=None, access=None, status=None, sort=None):
        """
        Finds all jobs in database matching search filters.
        """
        raise NotImplementedError

    def clear_jobs(self, request=None):
        """
        Removes all jobs from storage.
        """
        raise NotImplementedError
