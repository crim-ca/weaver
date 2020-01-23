class StoreInterface(object):
    type = None

    def __init__(self):
        if not self.type:
            raise NotImplementedError("Store 'type' must be overridden in inheriting class.")


class StoreServices(StoreInterface):
    type = "services"


class StoreProcesses(StoreInterface):
    type = "processes"


class StoreJobs(StoreInterface):
    type = "jobs"


class StoreQuotes(StoreInterface):
    type = "quotes"


class StoreBills(StoreInterface):
    type = "bills"
