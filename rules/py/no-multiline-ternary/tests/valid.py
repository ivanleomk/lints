def choose_url(is_prod: bool) -> str:
    if is_prod:
        return "https://api.example.com"
    return "http://localhost:8000"
