# Acervo Literário — Venda de Livros (Lince)

Catálogo estático do acervo pessoal do Rodrigo Hang, para venda entre colegas.
Três páginas, sem build e sem dependência de servidor — basta publicar na raiz do
repositório e o GitHub Pages serve tudo.

| Arquivo | O que é |
|---|---|
| `index.html` | Catálogo completo com busca, filtros, favoritos e **seleção múltipla** (carrinho) |
| `bookstore.html` | Página individual do livro — é o destino dos QR Codes (`?id=slug`) |
| `qrcodes.html` | Gerador de QR Code por livro, com impressão em A4 e sorteio semanal |

## Números do acervo

- **389 livros disponíveis** (+4 já vendidos), sendo **36 kits/coleções** e **353 avulsos**
- **28 sagas** identificadas (Harry Potter, Percy Jackson, Star Wars, Agatha Christie,
  Tolkien, Witcher, Desventuras em Série, Shadowhunters, Duna…)
- Preços entre **R$ 9 e R$ 502**, mediana **R$ 23** · total do acervo: **R$ 12.909**

## Como os preços foram calculados

O preço "de" é o valor de **livro novo hoje (set/2026)**, levantado nas editoras
(Rocco, Intrínseca, Aleph, HarperCollins, Galera/Record, WMF, Suma, Companhia das
Letras) e não mais o valor antigo da tabela.

O preço "por" sai de uma régua agressiva sobre esse valor, modulada pelo estado
descrito em cada anúncio:

| Estado | % do preço novo |
|---|---|
| Como novo — sem marcas | 33% |
| Ótimo — marcas mínimas | 29% |
| Bom — marcas de uso visíveis | 25% |

Kits e coleções recebem **12% a mais de desconto** sobre a soma dos volumes, para
premiar quem leva a saga inteira.

## Capas

Sistema em cascata, que nunca deixa um espaço vazio:

1. URL curada no cadastro (182 livros já têm)
2. Cache no navegador (`localStorage`)
3. Google Books API
4. Open Library
5. **Capa desenhada em SVG** — gerada na hora a partir do título, autor e saga,
   com paleta determinística. É o que aparece se tudo acima falhar.

Para fixar uma capa específica, preencha o campo `img` do livro no array `BOOKS`.

## Editar o catálogo

Os dados ficam no array `RAW` dentro de cada arquivo (mesmo conteúdo nos três).
Campos de cada livro:

| Campo | Significado |
|---|---|
| `slug` | Identificador na URL (`bookstore.html?id=slug`) — não mude depois de imprimir os QR |
| `t` / `tm` | Título completo / título curto exibido no card |
| `a` | Autor |
| `g` | Gêneros (array) |
| `v` | Preço de venda em reais (inteiro) |
| `op` | Preço de livro novo hoje |
| `cond` | `novo`, `otimo` ou `bom` |
| `sg` | Saga/série |
| `badge` | `kit` para coleções |
| `s` | `1` = vendido (o livro sai do catálogo e ganha selo) |
| `img` | URL da capa (opcional) |
| `d` | Descrição em blocos `Rótulo: texto`, separados por linha em branco |

**Para marcar um livro como vendido:** ache o slug e acrescente `"s":1`.
Lembre de alterar nos três arquivos.

## Publicar

```bash
git add index.html bookstore.html qrcodes.html README.md
git commit -m "Atualiza acervo"
git push
```

O GitHub Pages publica em `https://rodrigoch98.github.io/Sebo/`.

---

MIT © Rodrigo Hang
