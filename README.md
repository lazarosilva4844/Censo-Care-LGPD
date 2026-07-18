# Protótipo Simulador de Enquadramento de Grupo de Manutenção — v27 LGPD-safe + autenticação

Versão com entrada manual e autenticação simples por usuário e senha.

## Atualizações v27

- Mantido o modo **LGPD-safe**:
  - sem `base_clientes.csv`;
  - sem `veiculos_ativos.csv`;
  - sem consultas automáticas por CPF, CNPJ, placa ou chassi;
  - dados digitados manualmente.
- Incluída tela de **login antes do simulador**.
- Incluído botão **Sair**.
- Mantido o botão **Limpar todas as informações** dentro do simulador.
- Mantido o layout do PDF final.
- Mantida a regra crítica:
  - grupo final **Especial** sempre gera **controle por horas**.
- Mantido PDF em uma única página A4.
- Mantido suporte à fonte VW Headline OTF.

## Configuração de usuários no Streamlit Cloud

No Streamlit Cloud:

1. Abra o app.
2. Vá em **Manage app** ou **App settings**.
3. Acesse **Secrets**.
4. Cole o modelo abaixo:

```toml
[auth.users]
lazaro = "troque-por-uma-senha-forte"
consultor1 = "outra-senha-forte"
consultor2 = "mais-uma-senha-forte"
```

Depois salve e reinicie o app.

## Fallback local

Se nenhum Secret estiver configurado, o app permite teste local com:

```text
Usuário: admin
Senha: alterar123
```

Antes de usar em produção, configure os usuários em **Secrets**.

## Fonte VW Headline

O sistema busca a fonte em:

- `assets/vw-headline-book-587ebb6c67e7e.otf`
- `assets/fonts/vw-headline-book-587ebb6c67e7e.otf`

Por restrição de licenciamento, o pacote não redistribui arquivos de fonte.

## Como executar localmente

```powershell
cd caminho\da\pasta\prototipo_simulador_manutencao_v27
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Bases mantidas

A versão pública mantém apenas bases técnicas:

- `base_modelos.csv`
- `aplicacoes.csv`
- `implementos.csv`
- `intervalos.csv`
- `plano_contratos.csv`
