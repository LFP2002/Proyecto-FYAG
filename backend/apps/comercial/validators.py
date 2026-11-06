"""Normalización y validación reutilizable de RUT chileno."""

from django.core.exceptions import ValidationError


def _validar_cuerpo(cuerpo: str) -> None:
    if (
        not isinstance(cuerpo, str)
        or not cuerpo
        or not cuerpo.isascii()
        or not cuerpo.isdigit()
        or not any(digito != "0" for digito in cuerpo)
    ):
        raise ValidationError("El cuerpo del RUT debe ser numérico y no nulo.")


def normalizar_rut(value: str) -> str:
    """Devuelve CUERPO-DV; valida estructura, no la coincidencia del DV."""
    if not isinstance(value, str):
        raise ValidationError("El RUT debe ser un string.")

    rut = value.strip().upper()
    if not rut or rut.count("-") > 1:
        raise ValidationError("Formato de RUT inválido.")

    if "-" in rut:
        cuerpo, dv = rut.split("-")
    else:
        if "." in rut:
            raise ValidationError("El RUT con puntos requiere guion antes del DV.")
        cuerpo, dv = rut[:-1], rut[-1:]

    if len(dv) != 1 or dv not in "0123456789K":
        raise ValidationError("Dígito verificador inválido.")

    if "." in cuerpo:
        grupos = cuerpo.split(".")
        if not 1 <= len(grupos[0]) <= 3 or any(
            len(grupo) != 3 for grupo in grupos[1:]
        ):
            raise ValidationError("Agrupación de puntos inválida en el RUT.")

    cuerpo = cuerpo.replace(".", "")
    _validar_cuerpo(cuerpo)
    cuerpo = cuerpo.lstrip("0")
    return f"{cuerpo}-{dv}"


def calcular_dv_rut(cuerpo: str) -> str:
    """Calcula el dígito verificador mediante módulo 11."""
    _validar_cuerpo(cuerpo)
    suma = sum(
        int(digito) * (2 + indice % 6)
        for indice, digito in enumerate(reversed(cuerpo))
    )
    resultado = 11 - suma % 11
    if resultado == 11:
        return "0"
    if resultado == 10:
        return "K"
    return str(resultado)


def validar_rut(value: str) -> str:
    """Valida estructura y DV, devolviendo el RUT normalizado."""
    rut = normalizar_rut(value)
    cuerpo, dv = rut.split("-")
    if dv != calcular_dv_rut(cuerpo):
        raise ValidationError("El dígito verificador del RUT no coincide.")
    return rut
