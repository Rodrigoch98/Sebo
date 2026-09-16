# Acervo Literário — venda de livros (Lince)

Catálogo do acervo pessoal do Rodrigo Hang, para venda entre colegas.
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
| `acervo.js` | **O catálogo e as configurações. É o único arquivo que você edita** |
| `base.js` | Peças comuns às quatro páginas (formatação, capas, catálogo em memória) |
| `loja.js` | A loja ao vivo: reservas, vendas e o que some quando um exemplar sai |
| `firestore.rules` | Regras de segurança para colar no console do Firebase |
| `firebase.json` | Só para quem quiser publicar as regras pelo terminal |

> Antes os três HTMLs carregavam uma cópia do catálogo cada um — 1,6 MB somados e
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

1. O colega escolhe os livros e toca em **Reservar e falar no WhatsApp**.
2. Ele escreve o nome (e o setor, se quiser) e confirma.
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
| `img` | URL da capa (opcional) |
| `d` | Descrição em blocos `Rótulo: texto`, separados por linha em branco |

Um anúncio **sem** `parts` é um item físico único: um livro avulso ou um box que
você vende fechado. Um anúncio **com** `parts` é uma coleção montada a partir de
outros anúncios do site.

---

## Números do acervo

- **431 anúncios**: 353 avulsos e 78 kits/coleções, em 60 sagas
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

Cada anúncio mostra, nesta ordem: a **URL fixa** do campo `img`, e, se não houver,
uma **capa desenhada** na hora a partir do título, autor e saga.

Hoje: **198 anúncios com capa real** (as 182 originais mais 20 colhidas nos sites
das editoras) e **233 com capa desenhada**.

**A busca automática de capas foi desligada na prática.** A API do Google Books
tem cota diária e ela vive estourada — quando isso acontece nenhuma capa resolve,
e era isso que travava a página em carregamento infinito. O código ainda tenta,
mas agora: desiste depois de 4 recusas seguidas, tem prazo em cada busca, no
máximo 3 ao mesmo tempo, e **a capa desenhada entra sempre primeiro**. Nenhum card
fica girando, nem com a internet inteira fora do ar.

A Open Library, a outra fonte, praticamente não tem edição brasileira — testei
14 títulos e ela não achou nenhum.

**Para colocar uma capa real:** preencha o campo `img` do livro em `acervo.js` com
o endereço de uma imagem. Clicar com o botão direito numa capa no site da editora
e escolher "copiar endereço da imagem" resolve. Para as edições antigas, que saíram
de catálogo, a foto do seu próprio exemplar costuma ser a melhor opção — e vende
melhor do que a capa oficial, porque o comprador vê o livro que vai receber.

## Perguntas rápidas

**Vai custar alguma coisa?** Não. O plano gratuito do Firebase dá 50 mil leituras
por dia; o site só lê os exemplares reservados e vendidos, que são poucos.

**E se o Firebase sair do ar?** O site entra em *modo vitrine*: mostra tudo,
e o botão de compra volta a mandar a lista direto pelo WhatsApp. Nada quebra.

**Abrindo o arquivo no meu computador funciona?** As capas e o catálogo sim; a
loja ao vivo não (o Firebase só autoriza o domínio publicado). Aparece o modo
vitrine, que é o esperado.

**Alguém pode bagunçar meu acervo?** As regras só deixam um visitante *segurar* um
exemplar que esteja livre — ele não apaga reserva dos outros, não marca nada como
vendido e não lê o nome de quem comprou. Marcar vendido, liberar e ver os pedidos
é só com o seu login. Um engraçadinho ainda conseguiria reservar muita coisa de
uma vez; se isso acontecer, é só liberar pelo painel.

**Quero conferir as regras antes.** Console do Firebase → Firestore → Regras →
*Playground*: dá para simular leitura e escrita como visitante e como dono.

---

MIT © Rodrigo Hang
