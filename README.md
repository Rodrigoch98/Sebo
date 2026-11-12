# Acervo Literário — venda de livros (Lince)

Catálogo do acervo pessoal do Rodrigo Hang, para desapego no trabalho.
Site estático publicado no GitHub Pages, com **controle de estoque ao vivo** no
Firebase: quem reserva tira o livro da vitrine na hora, e a baixa da venda é
feita num painel, sem editar código.

Publica em `https://rodrigoch98.github.io/Sebo/`.

---

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | Catálogo: busca, filtros, favoritos, seleção múltipla e reserva |
| `bookstore.html` | Página individual do livro — destino dos QR Codes (`?id=slug`) |
| `qrcodes.html` | Gerador de QR Code por livro, impressão A4 e sorteio semanal |
| `admin.html` | **Painel do dono**: pedidos, confirmar venda, liberar reserva, baixa manual |
| `capas.html` | **Conferência e preenchimento das capas**, com exportação do `acervo.js` |
| `acervo.js` | **O catálogo e as configurações. É o único arquivo que você edita** |
| `base.js` | Peças comuns às páginas (formatação, capas, catálogo em memória) |
| `loja.js` | A loja ao vivo: reservas, vendas e o que some quando um exemplar sai |
| `firestore.rules` | Regras de segurança para colar no console do Firebase |
| `firebase.json` | Só para quem quiser publicar as regras pelo terminal |
| `fotos/` | Fotos dos seus exemplares usadas como capa (ver *Foto do seu exemplar*) |

> Antes cada HTML carregava uma cópia do catálogo — 1,6 MB somados e
> três lugares para errar. Agora o catálogo vive só em `acervo.js`: o total caiu
> para menos da metade e uma correção vale para o site inteiro.

---

## Ligar a loja (uma vez só)

No [console do Firebase](https://console.firebase.google.com), projeto **sebo-8820b**:

**1. Banco de dados**
Build → Firestore Database → *Criar banco de dados* → **modo de produção** →
região **southamerica-east1 (São Paulo)**. A região não muda depois.

**2. Regras**
Firestore → aba *Regras* → apague o que estiver lá, cole o conteúdo de
`firestore.rules` e publique.

**3. Login**
Build → Authentication → *Começar* → aba *Sign-in method* → ative dois:
- **Anônimo** — é o que identifica cada visitante para segurar a reserva no nome dele;
- **E-mail/senha** — é o seu login no painel.

**4. Sua conta de dono**
Authentication → aba *Users* → *Add user* → e-mail `rodrigocesarhang@gmail.com`
e uma senha sua. **Crie essa conta antes de publicar o site**: com ela existindo,
ninguém mais consegue registrar esse e-mail e virar dono.

**5. Liberar o domínio**
Authentication → *Settings* → *Authorized domains* → *Add domain* →
`rodrigoch98.github.io`. Sem isso o login não funciona no site publicado.

**6. Publicar**

```bash
git add .
git commit -m "Loja online com reserva e baixa automática"
git push
```

Pronto. Abra `admin.html` no site publicado e entre com o e-mail e a senha do passo 4.

> Trocar o e-mail do dono exige mudar em **dois** lugares: `dono:` em `acervo.js`
> e a linha marcada `// DONO` em `firestore.rules`.

---

## Como a venda funciona

1. A pessoa escolhe os livros e toca em **Reservar e falar no WhatsApp**.
2. Escreve o nome (e o setor, se quiser) e confirma.
3. Na mesma hora os exemplares somem da vitrine de todo mundo e o WhatsApp abre
   com a lista e o código do pedido.
4. O pedido aparece no painel como **aguardando você**.
5. Recebeu o pagamento? **Confirmar venda** — o exemplar sai do acervo de vez.
   Desistiu? **Liberar de volta** — volta para a vitrine na hora.

A reserva segura por **24 horas** (campo `horasReserva` em `acervo.js`). Passado
o prazo, os livros voltam sozinhos para a vitrine, sem você fazer nada.

**Vendeu no corredor?** Painel → aba *Acervo* → busque o título → *Marcar vendido*.

## Catálogo: filtros e topo

- Todo filtro funciona como interruptor: clicar de novo no que está marcado desmarca.
- Cada fileira de filtros (gêneros, sagas) ganha **Voltar ao início** assim que sai do
  começo, e **Limpar** quando tem algo marcado. Acima dos livros, as etiquetas mostram
  tudo o que está filtrando (busca e atalho inclusive) e **Limpar filtro** desfaz tudo.
- Os números do topo (livros à venda, menor preço, desconto médio, coleções) são
  calculados do acervo ao abrir a página. "Livros" conta exemplar físico: um box fechado
  vale pelos livros que tem dentro, e uma coleção montada não conta de novo os volumes.
- A vitrine em leque do topo escolhe sozinha as coleções com foto, uma por saga. Para
  escolher a dedo, preencha `destaques` em `acervo.js` com até 5 slugs.

---

## Anúncios sobrepostos — o problema que isso resolve

O mesmo exemplar aparece em até três anúncios: avulso, na coleção da série e no
box do universo. Se alguém leva o *Harry Potter e a Pedra Filosofal* avulso, a
coleção dos sete e o box do mundo bruxo deixam de existir — não dá para entregar
um conjunto sem uma das peças.

O site cuida disso sozinho. Cada coleção sabe quais anúncios ela cobre (campo
`parts`), e o estoque é controlado por **exemplar físico**, não por anúncio.
Quando um exemplar sai:

- **o anúncio que foi realmente vendido** fica marcado como *Vendido* e continua
  aparecendo na busca, para quem chegar pelo QR Code entender o que houve;
- **todos os outros anúncios que dependiam daquele exemplar somem** do site.

*Devolver à vitrine*, no painel, desfaz a venda inteira — clicando em qualquer um
dos anúncios afetados, não só no que foi vendido.

---

## Editar o catálogo

Tudo em `acervo.js`, no array `ACERVO_RAW`.

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
| `badge` | `kit` para coleções e boxes |
| `setOf` | Quantos livros a coleção ou o box tem |
| `parts` | Anúncios que a coleção cobre — **é o que faz os sobrepostos sumirem** |
| `box` | `1` = **box de verdade**, a caixa da editora. Mostra a foto da caixa e é vendido inteiro |
| `dentro` | Slug do box em que o volume mora. O volume **não sai sozinho** e some da vitrine |
| `conf` | `1` = estado conferido a olho nu, não é chute do cadastro |
| `s` | `1` = vendido direto no cadastro (fica fixo, o painel não mexe) |
| `img` | URL fixa da capa. É a única fonte de capa real do site |
| `alt` | Outros endereços da **mesma** capa (mesma edição), tentados em ordem se o `img` falhar. Nunca outra edição |
| `recorte` | `sim` força o robô a tirar o fundo (caixa fotografada em pé sobre branco); `nao` proíbe |
| `revisar` | `1` = capa achada automaticamente, edição ainda por conferir |
| `sug` | Imagens sugeridas esperando conferência em `capas.html` (a vitrine ignora) |
| `d` | Descrição em blocos `Rótulo: texto`, separados por linha em branco |

Um anúncio **sem** `parts` é um item físico único: um livro avulso ou um box que
você vende fechado. Um anúncio **com** `parts` é uma coleção montada a partir de
outros anúncios do site.

### Box ou coleção

- **Box** (`box: 1`) é a caixa da editora. Ele é vendido **sempre inteiro**: se os
  livros saíssem avulsos, a caixa sobraria e iria para o lixo. Por isso os volumes
  de um box levam `dentro: "<slug do box>"`: continuam no cadastro (para a montagem e
  para quem chegar por um QR antigo), mas não aparecem na vitrine nem na busca, e a
  página deles diz *Só no box* com um botão para o box.
- **Coleção** (sem `box`) é uma junta de livros soltos. Cada volume pode sair
  avulso, e a coleção some quando um deles sai. A capa da coleção é **sempre a
  montagem das capas dos volumes**, mesmo que exista foto: é o padrão de todas.
- Uma coleção pode juntar boxes: a *Coleção Agatha Christie* são os **9 boxes** da
  HarperCollins, e a *Coleção Duna* são os **2 boxes** da Aleph. Quem quiser separado
  leva box por box, nunca livro por livro.
- **"Box" no título só para caixa de verdade.** As antigas "Box Coleção" que são
  livros soltos (Harry Potter, Star Wars, Crônicas dos Kane, Magnus Chase, Provações de
  Apolo, Como Treinar o Seu Dragão, Gelo e Fogo, Ciclo A Herança, A Doutrina da Morte,
  A Rainha Vermelha) agora se chamam *Coleção* ou *Trilogia*. O endereço (`slug`)
  continua o mesmo, para não quebrar link nem QR code.
- Caixas confirmadas em nov/2026 (entrega 7): Desventuras em Série (13), The Witcher
  em capa dura (8), Os Instrumentos Mortais (6), As Peças Infernais (3), Os Artifícios
  das Trevas (3), Os Heróis do Olimpo (5 romances; *Os Diários do Semideus* é avulso),
  a trilogia O Senhor dos Anéis (3, dentro da *Coleção Tolkien* com os outros sete
  livros soltos) e O Essencial da Mitologia. O avulso "O Povo do Ar" saiu: O Povo do
  Ar é o próprio box.
- *Os Instrumentos Mortais*, *As Peças Infernais* e *Os Artifícios das Trevas* são as caixas de colecionador da
  Galera (as lombadas formam um desenho). O *Box O Povo do Ar* traz a trilogia de Jude e
  Cardan com *O Canto Mais Escuro da Floresta*. O box de *O Senhor dos Anéis* é o de
  capa preta, de 2019.
- Box sem foto aparece com a montagem dos volumes que vão dentro.

### Foto do seu exemplar (pasta `fotos/`)

Quando a capa da editora não existe na internet, ou a sua edição é diferente, a foto que
você tirar entra no site: a imagem vai para a pasta `fotos/` e o campo `img` do anúncio
recebe o caminho, sem http (ex.: `fotos/contos-de-fadas-dos-irmaos-grimm-capa-dura.jpg`).
O robô lê a foto direto do repositório e trata como qualquer outra capa. A primeira foi a
do *Contos de Fadas dos Irmãos Grimm*, já cortada rente à capa. A pasta `fotos/` faz
parte do site: envie junto com os outros arquivos.

---

## Números do acervo

- **446 anúncios** (nov/2026): avulsos, boxes e coleções. **79 volumes moram dentro de box**
  (`dentro`) e só saem com a caixa
- Avulsos de **R$ 9 a R$ 49** (somam R$ 7.969); coleções de **R$ 36 a R$ 569**
- Vitrine cheia: **R$ 17.408**
- **100 volumes já conferidos um a um** (campo `conf`), com o estado real e a
  observação do que foi visto; os outros seguem no estado do cadastro
- Estados hoje: 286 como novo · 113 ótimo · 31 bom
- Preço "de" = livro novo hoje (set/2026), levantado nas editoras
- Preço "por" = régua sobre esse valor, conforme o estado:

| Estado | % do preço novo |
|---|---|
| Como novo — sem marcas | 33% |
| Ótimo — marcas mínimas | 29% |
| Bom — marcas de uso visíveis | 25% |

Coleções de uma série levam **12% a mais** de desconto sobre a soma dos volumes;
os boxes de universo, **18%**. O preço da coleção é recalculado a partir dos
volumes sempre que um deles muda de estado.

## Capas

**A busca automática foi removida do código.** Antes o site perguntava a cada card
ao Google Books e à Open Library que capa usar, e era daí que vinham os dois
defeitos: a cota diária do Google estourava e o card ficava sem foto; e, quando
respondia, a busca casava só pelo título, sem saber de que edição era, e trazia a
capa americana no lugar da brasileira. Pior: quando uma URL do cadastro falhava, o
código saía procurando outra imagem, e era exatamente aí que a edição estrangeira
entrava sozinha no lugar da certa.

Agora a capa vem **só do que está escrito no cadastro**. A ordem é:

1. **coleção** (tem `parts`, não é `box`): sempre a **montagem dos volumes**;
2. **URL fixa** do campo `img` (livro avulso ou box), primeiro pela cópia tratada
   pelo robô em `capas/`, depois a URL e os endereços de `alt`;
3. **montagem dos volumes** quando a foto de um box falha;
4. **capa desenhada** na hora a partir do título, autor e saga.

**Capa só ao clicar (corrigido em nov/2026).** Do nono card em diante a capa não
aparecia na vitrine, só ao abrir o livro. A imagem de teste era criada fora da
página com `loading="lazy"`, e o Chrome nunca carrega imagem "lazy" que não está na
página. Agora o site espera o card chegar perto da tela e carrega normalmente.

**Fundo personalizado e sombra refeita.** Toda foto recortada (caixa, livro em 3D)
entra sobre o mesmo fundo escuro da montagem das coleções, e a sombra é desenhada
pelo site, igual para todas. A sombra que vinha na foto sai no robô.

Nenhuma dessas etapas depende de serviço de terceiros, e nenhuma pode trazer a capa
de outro livro. Com a internet inteira fora do ar, todo card continua com capa.

Hoje: **393 com URL fixa** e **41 com montagem dos volumes**. Nenhum anúncio
depende mais da capa desenhada. Ela continua no código como piso de segurança, para
o caso de uma URL sair do ar. Se a foto de uma **coleção** sair do ar, o card mostra a
montagem dos volumes no lugar dela, e não a capa desenhada.

Foto deitada ou quadrada que ainda não foi recortada aparece inteira, sem cortar as
laterais, sobre um fundo desfocado dela mesma.

**Montagem das coleções (entrega 10): um desenho só, o leque.**

- **Toda coleção** aparece em leque de três capas retas, o volume 1 no meio, na frente,
  o 2 à esquerda e o 3 à direita.
- Coleção feita **só de boxes** (Agatha Christie, 9 caixas; Duna, 2; Universo
  Shadowhunters, 3) abre o leque nos livros de dentro das caixas, um de cada box por
  vez: Duna mostra *Duna*, *Imperador-Deus de Duna* e *Messias de Duna*. A etiqueta diz
  "2 boxes · 6 livros". A grade de caixas da entrega 6 só volta se faltar capa de volume.
- Coleção **mista** (um box mais livros soltos, como ACOTAR, Dragões de Éter, O Povo do
  Ar) monta o leque só com os livros soltos: a foto da caixa no meio deles quebrava o
  desenho.
- No leque as capas têm a mesma largura e a proporção de cada uma fica entre 0,62 e
  0,75: o leque sai parelho e nenhuma capa sai esticada.
- **Capa avulsa ocupa o card inteiro** sempre que a proporção dela fica entre 0,58 e
  0,86. Livro de formato largo (Larousse, *Por Dentro da Série da HBO*) perde só uma
  faixa fina dos lados. Fora disso a capa entra inteira, sobre um fundo desfocado dela.

### Capas pelo ISBN da edição brasileira (nov/2026)

**132 livros** passaram a ter a capa endereçada pelo **ISBN da edição brasileira**,
de preferência a mais antiga (a primeira edição da editora que trouxe a série ao
Brasil). O ISBN de cada um foi conferido no Skoob, na editora ou em livraria, e a
capa vem do endereço da Amazon que é montado com esse ISBN
(`m.media-amazon.com/images/P/<ISBN-10>...`). Por ser o número da edição, não tem
como vir a capa americana.

Quando a Amazon não tem a foto daquele ISBN, ela devolve uma imagem de 1 pixel; o
site e o robô reconhecem isso e passam para os endereços de `alt`, todos da mesma
edição: a foto da capa no Skoob, a da própria editora (Record) e a da Open Library.

Também nesta rodada:

- 10 livros avulsos estavam com **foto da coleção inteira** (Divergente, Alien, Stranger
  Things, Neve e Cinzas, A Descoberta das Bruxas, A Rainha Vermelha, Irmãos de Sangue,
  Um de Nós Está Mentindo, Crepúsculo, O Poder Verdadeiro). A foto foi para a coleção e
  o livro ganhou a capa dele pelo ISBN;
- capas erradas trocadas pela edição brasileira: *O Código Da Vinci* (estava a
  americana), *Star Wars: Marcas da Guerra* e *O Oráculo* (a capa dele estava no
  *Escaravelho*);
- os 12 clássicos em capa dura (comprados na Livraria Família Cristã) usam as capas da
  **Editora Penkal Books**, a edição de verdade deles, pela foto da própria editora.
  *Poemas Escolhidos* é a antologia de **Gregório de Matos**. O Grimm usa a foto do seu
  exemplar (pasta `fotos/`);
- 11 caixas fotografadas em pé sobre fundo branco ganharam `recorte: "sim"`, para o
  robô tirar o fundo delas também.

### Entrega 10 (nov/2026)

- Capas trocadas: *Harry Potter e a Criança Amaldiçoada* volta para a edição de 2016 da
  Rocco (Partes Um e Dois); as duas *Alice* (DarkSide, Classic Edition) ganham a capa
  reta da Martins Fontes no lugar da foto 3D; *Box O Povo do Ar* e *Box Os Artifícios das
  Trevas* ganham a foto grande da caixa; *Círculo Negro* (Bertrand, 2010) e *Mitologia
  Nórdica* (Intrínseca, capa dura) ganham capa reta em tamanho bom; *O Morro dos Ventos
  Uivantes* usa a foto grande da Penkal (a mesma edição azul).
- *O Cálice dos Deuses* saiu do acervo (só existe em e-book). A Coleção Percy Jackson
  ficou com 8 volumes (R$ 178) e o Universo Rick Riordan com 31 livros (R$ 569).

### Fotos de coleção da sua lista

Das 52 imagens que você levantou, 36 já estavam no site (a maioria é capa de volume 1 e
foi para o livro avulso). Oito eram fotos de coleção com destino certo e viraram a capa
da coleção: Maze Runner, Trilogia Halo, Fronteiras do Universo, Silo, C.J. Tudor, Trono
de Vidro, O Clã dos Magos (Mago Negro) e Os Legados de Lorien. A da Maze Runner veio com
o endereço quebrado (molde `{w}x{h}` sem preencher) e foi corrigida para o formato
420x420 das outras imagens da Magalu.

As outras oito não dava para afirmar de qual livro são sem olhar. Depois de conferidas
uma a uma, quatro viraram a capa da coleção certa (Nárnia, Clássicos Brasileiros,
Splintered e Encantadas) e quatro não eram de nenhum anúncio e saíram. A Maze Runner
voltou para a montagem dos volumes: a Magalu bloqueia o robô, e com os seis volumes
agora com capa, a montagem mostra a coleção melhor do que a foto.

O campo `sug` continua existindo para as próximas imagens que você mandar: elas aparecem
na aba **Imagens da sua lista** de `capas.html`, com dois botões: *Usar esta capa* e
*Não é deste livro*. A vitrine nunca mostra o que está em `sug`.

As coleções sem foto continuam com a montagem das capas dos volumes, que mostra
exatamente o que vai junto e melhora sozinha a cada capa de volume preenchida.

### A página `capas.html`

É por ela que as capas que faltam entram, sem editar código:

- **Conferir as URLs** abre cada capa do cadastro no seu navegador e lista as que
  não carregaram. Só um navegador de verdade, na sua rede, sabe isso: um site pode
  bloquear a imagem para quem vem de fora, e isso só aparece na prática.
- **Colar o endereço** de uma imagem troca a miniatura na hora. É essa conferência
  com o olho que garante que a capa é da edição brasileira certa, e não a americana.
- **Amazon / Estante / Imagens** abrem a busca daquele título já preenchida.
- **Imagens da sua lista** mostra as imagens sugeridas que esperam a sua decisão.
  Ao usar uma imagem num anúncio, ela sai sozinha da sugestão dos outros.
- **Baixar acervo.js** devolve o arquivo inteiro já com as capas e decisões dentro.
  Você só substitui o arquivo no repositório e dá `git push`.

Quinze anúncios seguem com `revisar: 1` e aparecem na aba *Conferir edição*: os
Star Wars colhidos em sites de resenha (a Aleph tirou a linha do catálogo), as duas
edições de *Animais Fantásticos* e outros que esperam o ISBN do seu exemplar.

**Sobre os Agatha Christie:** são os **9 boxes da coleção da HarperCollins** (3 livros
cada). Cada box tem a foto da caixa e é vendido inteiro; a coleção completa junta os
nove. As capas dos volumes, que só aparecem na montagem, são da mesma edição dos boxes.

**Para as edições antigas, que saíram de catálogo**, a foto do seu próprio exemplar
costuma ser a melhor opção, e vende melhor do que a capa oficial, porque o comprador
vê o livro que vai receber.

## Robô de capas

A cada publicação, o GitHub roda duas tarefas sozinho (arquivo
`.github/workflows/publicar.yml`):

**1. Publicar** (`ferramentas/capas.py`), alguns minutos:

- baixa cada capa do cadastro direto da loja de origem; se o endereço falhar (ou
  devolver a imagem de 1 pixel da Amazon), tenta os de `alt`, na ordem;
- **tira o fundo** das fotos de caixa, kit e pilha de livros quando o fundo é liso
  (branco de loja), deixando o fundo transparente, e **tira junto a sombra** que a
  foto trazia (o site desenha uma nova). Capa reta com moldura branca em volta é
  cortada rente e continua capa. Capa de livro justa nunca é recortada;
- para separar sombra de objeto e devolver partes brancas que o fundo engoliu (a
  lombada branca de um box, por exemplo), o robô usa uma **IA de recorte** (rembg),
  que ele mesmo instala na primeira vez. Se ela discordar demais do recorte por cor,
  vale o recorte por cor com limpeza de sombra. Foto de box com `recorte: "sim"` em
  fundo que não é liso também passa pela IA, com conferência de que o recorte pegou
  a caixa inteira;
- guarda uma cópia leve **dentro do próprio site**, em `capas/<slug>.webp` (WebP com
  transparência: o mesmo fundo transparente do PNG com uma fração do peso). Para
  gerar PNG, mude `FORMATO` no começo do script;
- publica o site.

**Versão 4 do tratamento (entrega 6):**

- **livro avulso vira capa reta** que ocupa o card inteiro, como uma capa escaneada.
  Foto de livro em 3D, em pé, com lombada, páginas, sombra ou fundo branco: o robô acha
  os quatro cantos da frente do livro, endireita a perspectiva e corta rente. O topo
  nunca é cortado (é onde fica o título); lombada e páginas só saem pelos lados, chão
  claro só por baixo. Se não der para achar a frente com segurança, fica o recorte
  sobre o fundo do site, como antes;
- **box sem chão**: sai a faixa clara que a foto trazia embaixo da caixa (reflexo,
  filete branco). Caixa branca em fundo branco, que o recorte por cor não separa, é
  recortada pelo contorno das quinas, lombadas e dourados;
- **versão maior da mesma imagem**: antes de tratar, o robô tenta o endereço da imagem
  em tamanho maior (Amazon sem o tamanho no nome, Mercado Livre 2X, WordPress sem o
  `-300x450`, Skoob sem o redimensionador, Estante Virtual sem o corte). Ela só é usada
  se for mesmo maior e tiver o mesmo desenho e a mesma proporção da original;
- **imagem pequena** é ampliada até 720 px com reforço leve de nitidez (fica mais
  nítida que a ampliação do navegador), e as cópias passam a ter até 900 px;
- capa reta que já estava certa continua igual: só ganha a versão maior e a nitidez.
  Na conferência feita antes da entrega, das 303 capas retas só uma mudou de desenho
  (*A Luneta Âmbar*, que perdeu a margem branca e de qualquer forma trocou de edição).

**Versão 5 do tratamento (entrega 10):**

- **a lombada sai inteira.** Na foto 3D da loja (livro girado, lombada à mostra) o robô
  acha o topo e a base da capa como as retas mais longas do contorno e a dobra
  lombada/capa pela quebra do topo. A versão 4 deixava uma faixa da lombada na
  esquerda (*Eclipse*, *Fios de Prata*, *O Livro da Vida*, *Sombra da Noite*,
  *A Essência do Mal*);
- **a capa volta à proporção de livro.** Livro girado aparece mais estreito do que é;
  endireitado, ficava comprido, "esticado" (era o defeito da Trilogia All Souls). Agora
  a capa endireitada volta para 0,68 quando sai mais estreita que 0,66;
- **livro de estúdio vira capa reta**: fundo cinza em degradê, reflexo no chão (as fotos
  da Penkal dos 12 clássicos, *Robô Selvagem*, *O Morro dos Ventos Uivantes*). O robô só
  corta quando o quadro achado tem **borda de verdade na foto**: capa de desenho branco,
  como *Trono de Vidro*, nunca é mexida;
- **box sem casco**: a versão 4 fechava com branco o vão entre a caixa e os livros
  abertos em leque (*A Saga dos Corvos*, *Os Artifícios das Trevas*). Agora sai só o
  fundo liso ligado à borda, e o vão fica vazio. Frente chapada de caixa branca (só o
  emblema no branco, como a do box branco de *Jogos Vorazes*) fica como veio, sem
  recorte;
- **box sem fiapo**: sai o risco fino de chão ou de sombra (branco, cinza ou preto) que
  sobrava embaixo da caixa (*Machado de Assis*, *Princesa das Cinzas*, *Agatha 7*,
  *Tempest*, *ACOTAR*). Friso colorido da caixa fica;
- **contorno liso**: recorte pequeno ampliado (*O Essencial da Mitologia*, *Os Heróis do
  Olimpo*) saía serrilhado; o contorno agora é alisado na escala nova;
- **versão maior** também na VTEX (Martins Fontes, sem o `-292-292`) e no WordPress
  com corte pedido na URL (`?w=250&h=420&crop`).

A versão 5 reprocessa todas as capas uma vez, na próxima publicação.

A vitrine usa a cópia guardada primeiro: carrega mais rápido, não depende de loja
nenhuma e não sofre com site que bloqueia imagem "emprestada". Sem a cópia, vale a
URL do cadastro, como antes. Imagem já tratada não é baixada de novo.

O resultado fica em `capas/relatorio.json` e nas folhas de conferência em
`capas/conferencia/`, agora sobre fundo escuro, para sobra de fundo branco ou de
sombra aparecer na hora. Em `capas.html`, a aba **Precisa de outra imagem** lista as
fotos com cenário (fundo que não dá para tirar) e as que o robô não conseguiu baixar.

**2. Pesquisar** (`ferramentas/pesquisa.py`), em paralelo, até meia hora na
primeira vez:

- para cada livro avulso que ainda não tem a capa pelo ISBN brasileiro, procura as
  edições no Google Books e na Open Library (os que já têm ficam de fora);
- fica só com as **edições brasileiras** (ISBN 978-85 ou 978-65), da mais antiga
  para a mais nova;
- baixa a capa de cada edição e monta folhas em `pesquisa/folha-NN.jpg`: a capa atual
  do site ao lado das candidatas, com ano e editora. O índice está em
  `pesquisa/indice.txt`.

A pesquisa não muda o site: ela serve para escolher a capa certa com o olho. Só
pesquisa o que é novo; para refazer um livro com outra busca, escreva em
`pesquisa/pedidos.txt` uma linha `slug | título | autor`. Se o Google limitar as
consultas, o resto fica para a próxima publicação; com uma chave da API do Google
Books no segredo `GOOGLE_BOOKS_KEY` do repositório, o limite deixa de existir.

### Ligar o robô (uma vez só)

1. **Settings → Pages → Build and deployment → Source**: troque para **GitHub
   Actions**.
2. Envie o **pacote completo do site** (todos os arquivos e a pasta `ferramentas/`).
   Se o envio deixar faltar algum arquivo essencial (`acervo.js`, `loja.js`, as
   páginas), o robô para antes de publicar e avisa quais faltam: o site que está no
   ar continua como estava. As pastas `capas/` e `pesquisa/` são **do robô**: não
   precisa enviar nem apagar. Se forem apagadas, nada quebra, só que a próxima
   passada baixa todas as capas de novo e demora mais.
3. **Add file → Create new file**, com o nome `.github/workflows/publicar.yml`, cole
   o conteúdo do arquivo e confirme. Esse envio já dispara a primeira passada; o
   andamento aparece na aba **Actions**.

## Perguntas rápidas

**Vai custar alguma coisa?** Não. O plano gratuito do Firebase dá 50 mil leituras
por dia; o site só lê os exemplares reservados e vendidos, que são poucos.

**E se o Firebase sair do ar?** O site entra em *modo vitrine*: mostra tudo,
e o botão de compra volta a mandar a lista direto pelo WhatsApp. Nada quebra.

**Abrindo o arquivo no meu computador funciona?** As capas e o catálogo sim; a
loja ao vivo não (o Firebase só autoriza o domínio publicado). Aparece o modo
vitrine, que é o esperado.

**Uma capa sumiu do site. O que houve?** A URL daquele anúncio parou de responder,
e o card voltou para a capa desenhada em vez de inventar outra. Abra `capas.html`,
rode *Conferir as URLs* e a aba *Não carregou* mostra exatamente quais trocar.

**Alguém pode bagunçar meu acervo?** As regras só deixam um visitante *segurar* um
exemplar que esteja livre — ele não apaga reserva dos outros, não marca nada como
vendido e não lê o nome de quem comprou. Marcar vendido, liberar e ver os pedidos
é só com o seu login. Um engraçadinho ainda conseguiria reservar muita coisa de
uma vez; se isso acontecer, é só liberar pelo painel.

**Quero conferir as regras antes.** Console do Firebase → Firestore → Regras →
*Playground*: dá para simular leitura e escrita como visitante e como dono.

---

MIT © Rodrigo Hang
