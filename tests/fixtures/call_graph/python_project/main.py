from utils import load_data, save
from service import process, greet


def main():
    load_data()
    process()
    save()
    greet("world")


def run():
    main()


class UserService:
    def get_user(self, uid):
        return self._fetch(uid)

    def delete_user(self, uid):
        pass

    def _fetch(self, uid):
        return {}


def farewell():
    pass
