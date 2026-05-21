from .models import ExchangeRate

def exchange_rate_context(request):
    """
    Inyecta la tasa de cambio actual (VES/USD) en el contexto de todos los templates.
    """
    return {
        'latest_rate': ExchangeRate.get_latest()
    }
