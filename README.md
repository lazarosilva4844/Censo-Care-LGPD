# Protótipo Simulador de Enquadramento de Grupo de Manutenção — v31

Versão funcional com atualização visual da tela de login e do cabeçalho após autenticação.

## Atualizações v31

- Tela de login:
  - utiliza a fotografia real enviada pelo usuário;
  - aplicação de tratamento azulado sobre a imagem original;
  - card centralizado e mais minimalista;
  - logo original Futura Caminhões / VWCO preservada, sem barra entre as marcas;
  - removido o subtítulo do login;
  - botão **Entrar** mantido.
- Área autenticada:
  - cabeçalho branco corporativo;
  - logo e título organizados em áreas distintas;
  - detalhes em azul-claro, sem uso de amarelo;
  - melhor alinhamento e espaçamento visual.
- Mantido sem alterações:
  - regras de classificação;
  - autenticação via Streamlit Secrets;
  - entrada manual de dados;
  - geração do PDF;
  - regras do Grupo Especial por horas;
  - bases CSV e funcionalidades da versão anterior.

## Configuração de usuários no Streamlit Cloud

```toml
[auth.users]
"lazaro@futuracaminhoes.com.br" = "troque-por-uma-senha-forte"
"consultor@futuracaminhoes.com.br" = "outra-senha-forte"
```

## Execução local

1. Instale as dependências:

```bash
pip install -r requirements.txt
```

2. Crie `.streamlit/secrets.toml` com os usuários autorizados.
3. Execute:

```bash
streamlit run app.py
```

## Estrutura esperada no GitHub

```text
assets/
data/
README.md
app.py
requirements.txt
```
