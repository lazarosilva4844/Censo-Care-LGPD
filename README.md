# Protótipo Simulador de Enquadramento de Grupo de Manutenção — v33

Versão funcional com a fotografia real do Meteor enviada pelo usuário aplicada ao fundo do login, com tratamento azulado, mantendo o cabeçalho aprovado e as funcionalidades existentes.

## Atualizações v33

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


## Atualização visual v33
- Navegação lateral azul com Início, Simulador, Consultas, Relatórios, Cadastros e Sair.
- Cabeçalho funcional com logo original, título, Limpar dados e identificação do usuário.
- Login com fotografia real enviada pelo usuário e tratamento azulado.
- Regras e funcionalidades do simulador preservadas.
