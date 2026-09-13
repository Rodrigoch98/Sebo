# Acervo Literário — Venda de Livros (Lince)

Catálogo estático do acervo pessoal do Rodrigo Hang, para venda entre colegas.
Três páginas, sem build e sem servidor: basta publicar na raiz do repositório.

| Arquivo | O que é |
|---|---|
| `index.html` | Catálogo completo com busca, filtros, favoritos e **seleção múltipla** (carrinho) |
| `bookstore.html` | Página individual do livro — destino dos QR Codes (`?id=slug`) |
| `qrcodes.html` | Gerador de QR Code por livro, impressão A4 e sorteio semanal |

## Números do acervo

- **431 anúncios disponíveis**: 353 exemplares avulsos e **78 kits/coleções**
- **60 sagas** identificadas
- Avulsos de **R$ 9 a R$ 49**, somando **R$ 8.105**
- Coleções de **R$ 40 a R$ 1.166**

## Como os preços foram calculados

O preço "de" é o valor de **livro novo hoje (set/2026)**, levantado nas editoras
(Rocco, Intrínseca, Aleph, HarperCollins, Galera/Record, WMF, Suma, Companhia das
Letras), não mais o valor antigo da tabela. Isso vale para **todos** os anúncios,
inclusive os 182 que já estavam no site.

O preço "por" sai de uma régua agressiva sobre esse valor, modulada pelo estado
descrito em cada anúncio:

| Estado | % do preço novo |
|---|---|
| Como novo — sem marcas | 33% |
| Ótimo — marcas mínimas | 29% |
| Bom — marcas de uso visíveis | 25% |

Coleções de uma série levam **12% a mais** de desconto sobre a soma dos volumes.
Os cinco boxes de universo (Rick Riordan, Shadowhunters, Sarah J. Maas, Mundo
Bruxo e James Dashner) levam **18%**.

## Coleções sobrepostas — atenção ao marcar vendido

Um mesmo livro pode aparecer em três anúncios ao mesmo tempo: avulso, na coleção
da série e no box do universo. Isso é proposital (quem quer um leva um, quem é fã
leva tudo), mas exige cuidado na baixa.

Cada anúncio de coleção traz o campo `parts`, com os slugs de tudo que ele inclui.
Ao vender uma coleção, marque `"s":1` também em cada slug listado ali. Ao vender um
avulso, marque `"s":1` nele e confira se alguma coleção que o contém ficou
incompleta.

## Capas

Sistema em cascata, que nunca deixa espaço vazio:

1. URL curada no cadastro (182 livros já têm)
2. Cache no navegador (`localStorage`)
3. Google Books API
4. Open Library
5. **Capa desenhada em SVG** — gerada na hora a partir do título, autor e saga

Para fixar uma capa específica, preencha o campo `img` do livro.

## Editar o catálogo

Os dados ficam no array `RAW` dentro de cada arquivo (mesmo conteúdo nos três).

| Campo | Significado |
|---|---|
| `slug` | Identificador na URL — não mude depois de imprimir os QR |
| `t` / `tm` | Título completo / título curto exibido no card |
| `a` | Autor |
| `g` | Gêneros (array) |
| `v` | Preço de venda em reais (inteiro) |
| `op` | Preço de livro novo hoje |
| `cond` | `novo`, `otimo` ou `bom` |
| `sg` | Saga/série |
| `badge` | `kit` para coleções |
| `setOf` | Quantos livros a coleção tem |
| `parts` | Slugs incluídos na coleção |
| `s` | `1` = vendido |
| `img` | URL da capa (opcional) |
| `d` | Descrição em blocos `Rótulo: texto`, separados por linha em branco |

Alterações precisam ser feitas nos três arquivos.

## Publicar

```bash
git add index.html bookstore.html qrcodes.html README.md
git commit -m "Atualiza acervo"
git push
```

Publica em `https://rodrigoch98.github.io/Sebo/`.

---

MIT © Rodrigo Hang
