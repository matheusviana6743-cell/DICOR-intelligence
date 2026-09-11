# -*- coding: utf-8 -*-
"""DICOR Central V705 - acabamento final sobre a V704.
Inclui busca rápida na home sem reintroduzir módulos operacionais na primeira tela.
"""
import central_home_v700 as v700
import central_home_v704 as v704


def _home_with_search(u):
    html = v704._home(u)
    marker = '<div class="section-head"><span class="kicker">MONITORAMENTO</span><h2>PROCURADOS EM DESTAQUE</h2></div>'
    search = '<section class="panel search-panel"><form class="search-form" method="get" action="/procurados"><input name="q" maxlength="120" placeholder="Pesquisar por nome, RG, passaporte ou crime"><button class="btn gold">PESQUISAR →</button></form></section>'
    return html.replace(marker, search + marker, 1)


def install(bot_module):
    central = v704.install(bot_module)
    v700.home = _home_with_search
    return central
