def choose_url(is_prod: bool) -> str:
    return (
        "https://api.example.com"
        if is_prod
        else "http://localhost:8000"
    )
