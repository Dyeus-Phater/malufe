# Banana Vision (Python)

Aplicativo desktop em Python inspirado no Banana Vision web, voltado para visualização e edição de textos para romhacking, tradução e desenvolvimento. Ele roda localmente, sem envio de dados.

## Principais recursos

- Carregamento de múltiplos scripts e comparação com dois scripts originais.
- Separação de blocos por linha, linhas vazias, tag customizada ou regex.
- Preview com caixa configurável, zoom, fundo por cor/imagem e exportação PNG.
- Fonte de sistema com carregamento TTF/OTF, outline e sombra.
- Detecção de overflow por caracteres e limite de bytes.
- Localizar/Substituir, glossário, progresso de tradução.
- Salvamento de projeto, perfis de configuração e auto-save.
- Integração básica com GitHub (carregar/salvar arquivos via API).

## Requisitos

- Python 3.10+
- Pillow

Instalação de dependências:

```bash
pip install -r requirements.txt
```

## Como executar

```bash
python banana_vision_app.py
```

## Dicas de uso rápido

1. **File > Load Script** para abrir scripts principais.
2. **File > Load Original 1/2** para comparação.
3. Ajuste fonte, preview e tags nas abas **Fonts** e **Settings**.
4. Use **Export Preview PNG** para gerar a imagem do diálogo.
5. Salve o projeto para retomar depois.

## Estrutura do projeto

- `banana_vision_app.py`: app principal.
- `requirements.txt`: dependências.

## Observações

Este app é um protótipo funcional com foco em fluxo de trabalho local. Recursos avançados (como editor de mapa de caracteres bitmap e renderização VWF completa) podem ser expandidos conforme a necessidade.
