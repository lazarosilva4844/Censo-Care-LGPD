# Protótipo Simulador de Enquadramento de Grupo de Manutenção — v29

Versão com layout ajustado conforme orientação do arquivo "Prompts - Layout.docx".

## Atualizações v29

- Login no padrão solicitado:
  - logotipo Futura / VWCO;
  - título "Login";
  - campos de acesso;
  - removida nota "Para produção...".
- Página inicial ajustada:
  - incluída logotipo Futura / VWCO;
  - título alterado para "Classificação de grupo de manutenção";
  - removido subtítulo;
  - removidas informações visíveis de versão e LGPD da área principal.
- Botão de limpeza ajustado:
  - texto alterado para "Limpar dados";
  - posicionado no canto superior direito;
  - estilo azul.
- Mantido:
  - autenticação por Streamlit Secrets;
  - bloqueio sem usuários configurados;
  - modo LGPD-safe;
  - entrada manual dos dados;
  - layout do PDF sem alterações;
  - Grupo Especial com controle por horas.

## Configuração de usuários no Streamlit Cloud

```toml
[auth.users]
"lazaro@futuracaminhoes.com.br" = "troque-por-uma-senha-forte"
"consultor@futuracaminhoes.com.br" = "outra-senha-forte"
```

## Estrutura esperada no GitHub

```text
assets/
data/
README.md
app.py
requirements.txt
```

## Bases mantidas

A versão mantém apenas bases técnicas:

- `base_modelos.csv`
- `aplicacoes.csv`
- `implementos.csv`
- `intervalos.csv`
- `plano_contratos.csv`
