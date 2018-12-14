
def includeme(config):
    from twitcher.database.base import get_database_factory
    config.registry.db = get_database_factory(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, 'db', reify=True)
