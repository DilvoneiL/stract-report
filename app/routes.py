from __future__ import annotations

from flask import Blueprint
from .services import (
    general_ads_table, general_summary_table,
    platform_ads_table, platform_summary_table,
    build_csv_response,
)

bp = Blueprint("reports", __name__)

@bp.get("/")
def root():
    name = "dilvonei"
    email = "dilvoneialveslacerdajunior@gmail.com"
    linkedin = "https://www.linkedin.com/in/dilvonei-alves-lacerda-05328a228/"
    return f"{name}\n{email}\n{linkedin}\n"

@bp.get("/geral")
def geral():
    rows, headers = general_ads_table()
    return build_csv_response(rows, headers, "geral.csv")

@bp.get("/geral/resumo")
def geral_resumo():
    rows, headers = general_summary_table()
    return build_csv_response(rows, headers, "geral_resumo.csv")

@bp.get("/<platform>")
def plataforma(platform: str):
    rows, headers = platform_ads_table(platform)
    return build_csv_response(rows, headers, f"{platform}.csv")

@bp.get("/<platform>/resumo")
def plataforma_resumo(platform: str):
    rows, headers = platform_summary_table(platform)
    return build_csv_response(rows, headers, f"{platform}_resumo.csv")
