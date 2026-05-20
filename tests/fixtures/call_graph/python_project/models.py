"""Models with class methods."""


class UserService:
    def get_user(self, uid):
        return self._fetch(uid)

    def _fetch(self, uid):
        return {"id": uid, "name": "Alice"}

    def delete_user(self, uid):
        self._fetch(uid)
        return True
