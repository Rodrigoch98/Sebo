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
| `badge` | `kit` para coleções |
| `setOf` | Quantos livros a coleção tem |
| `parts` | Anúncios que a coleção cobre — **é o que faz os sobrepostos sumirem** |
| `conf` | `1` = estado conferido a olho nu, não é chute do cadastro |
| `s` | `1` = vendido direto no cadastro (fica fixo, o painel não mexe) |
| `img` | URL fixa da capa. É a única fonte de capa real do site |
| `revisar` | `1` = capa achada automaticamente, edição ainda por conferir |
| `d` | Descrição em blocos `Rótulo: texto`, separados por linha em branco |

Um anúncio **sem** `parts` é um item físico único: um livro avulso ou um box que
você vende fechado. Um anúncio **com** `parts` é uma coleção montada a partir de
outros anúncios do site.

---

## Números do acervo

- **435 anúncios**: 355 avulsos e 80 kits/coleções, em 61 sagas
- Avulsos de **R$ 9 a R$ 49** (somam R$ 8.020); coleções de **R$ 36 a R$ 588**
- Vitrine cheia: **R$ 17.476**
- **100 volumes já conferidos um a um** (campo `conf`), com o estado real e a
  observação do que foi visto; os outros seguem no estado do cadastro
- Estados hoje: 287 como novo · 113 ótimo · 31 bom
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

1. **URL fixa** do campo `img`, escolhida e conferida por você;
2. **montagem dos volumes**, quando o anúncio é uma coleção montada (campo `parts`);
3. **capa desenhada** na hora a partir do título, autor e saga.

Nenhuma dessas etapas depende de serviço de terceiros, e nenhuma pode trazer a capa
de outro livro. Com a internet inteira fora do ar, todo card continua com capa.

Hoje: **373 com URL fixa** e **62 com montagem dos volumes**. Nenhum anúncio
depende mais da capa desenhada. Ela continua no código como piso de segurança, para
o caso de uma URL sair do ar.

A maioria das URLs vem dos sites das próprias editoras brasileiras, onde a edição é
a certa por definição: Amazon (188), Shopify da Record/HarperCollins/Aleph (52),
Intrínseca (45), Companhia das Letras (25) e Rocco (23). Os títulos fora de catálogo
saíram de catálogos especializados e livrarias: Proibido Ler (9), Delicious Death
(6), Touché Livros (4) e alguns avulsos.

### Por que as coleções não têm foto de caixa

Os 18 boxes que existem como produto de verdade já têm capa. As outras 62 coleções
são conjuntos que **você montou** a partir de anúncios do site: não existe caixa,
não existe foto de produto para procurar em lugar nenhum. A capa delas é a montagem
das capas dos próprios volumes, que mostra exatamente o que vai junto e melhora
sozinha a cada capa de volume que você preencher.

### A página `capas.html`

É por ela que as capas que faltam entram, sem editar código:

- **Conferir as URLs** abre cada capa do cadastro no seu navegador e lista as que
  não carregaram. Só um navegador de verdade, na sua rede, sabe isso: um site pode
  bloquear a imagem para quem vem de fora, e isso só aparece na prática.
- **Colar o endereço** de uma imagem troca a miniatura na hora. É essa conferência
  com o olho que garante que a capa é da edição brasileira certa, e não a americana.
- **Amazon / Estante / Imagens** abrem a busca daquele título já preenchida.
- **Baixar acervo.js** devolve o arquivo inteiro já com as capas dentro. Você só
  substitui o arquivo no repositório e dá `git push`.

Trinta anúncios estão marcados com `revisar: 1` e aparecem na aba *Conferir
edição*. São os casos em que a capa foi achada mas a edição merece seu olho:

- os **7 Harry Potter**, agora no conjunto clássico da Rocco (ISBNs sequenciais
  978-85-325-3078-3 a 978-85-325-3084-4), que combina com exemplares mais antigos;
- **3 Agatha Christie** cujo título de tradução difere do seu exemplar (*O Natal de
  Hercule Poirot*, *Cai o pano*, *Elefantes nunca esquecem*);
- **9 Star Wars** e 1 outro colhidos em sites de resenha, não na editora, porque a
  Aleph tirou a linha Star Wars do catálogo;
- alguns com duas edições de mesmo título (*Animais Fantásticos e Onde Habitam*);
- os dois volumes de *O Essencial da Mitologia*, que dividem a mesma foto de caixa
  porque não achei as capas individuais.

**Sobre os 23 Agatha Christie:** usei as capas da HarperCollins, que é quem publica
a obra completa no Brasil e vende justamente em coleção. Mas seis dos seus títulos
(*Os Trabalhos de Hércules*, *A Maldição do Espelho*, *A Casa do Penhasco*, *Treze à
Mesa*, *Poirot Perde uma Cliente*, *Detetive Parker Pyne*) são traduções que a Nova
Fronteira também usou. Se os seus exemplares forem Nova Fronteira, a arte é outra.
Vale conferir na página.

**Para as edições antigas, que saíram de catálogo**, a foto do seu próprio exemplar
costuma ser a melhor opção, e vende melhor do que a capa oficial, porque o comprador
vê o livro que vai receber.

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
