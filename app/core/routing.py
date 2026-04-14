from fastapi.routing import APIRoute


class AliasRoute(APIRoute):
    """
    Custom route class that serializes all response models using their field
    aliases (camelCase JSON) by default, without having to set
    response_model_by_alias=True on every single endpoint.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("response_model_by_alias", True)
        super().__init__(*args, **kwargs)