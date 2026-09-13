/*
 * Builds Phil_White_Paper.docx from data/legal_docs.json.
 *
 * The docx used to be maintained by hand, so it drifted: it still said
 * "twelve courses" six times after the website had been updated to twenty, and
 * was missing the eight course rows and sources added with them. Generating it
 * from the same source the website reads means the two cannot disagree again.
 *
 * Re-run after editing legal_docs.json.
 */
const { Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType,
        HeadingLevel, BorderStyle } = require('docx');
const fs = require('fs');

const TEAL = "0F6E56", NAVY = "12263A", INK = "2B2A26", MUTED = "5F5E5A";
const SOURCE = '/home/claude/legal_docs.json';
const blocks = JSON.parse(fs.readFileSync(SOURCE, 'utf8')).white_paper;

const body = (text, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 140, line: 300 },
  alignment: o.align,
  children: [new TextRun({
    text, size: o.size ?? 21, color: o.color ?? INK, bold: o.bold,
    italics: o.italics, font: "Calibri", characterSpacing: o.spacing,
  })],
});

const children = [];

// The first six blocks are the title page: eyebrow, "White paper", title,
// standfirst, author, date. They are laid out rather than run through the
// generic handler, which would render them as body paragraphs.
const [eyebrow, kind, title, standfirst, author, date] = blocks.slice(0, 6).map(b => b[1]);

children.push(
  new Paragraph({ children: [new ImageRun({
    data: fs.readFileSync('/home/claude/mark-512.png'),
    transformation: { width: 46, height: 46 } })], spacing: { after: 180 } }),
  body(eyebrow, { size: 17, bold: true, color: TEAL, spacing: 40, after: 80 }),
  body(kind, { size: 17, color: MUTED, after: 220 }),
  new Paragraph({
    spacing: { after: 180, line: 320 },
    children: [new TextRun({ text: title, size: 40, bold: true, color: NAVY,
                             font: "Calibri" })],
  }),
  body(standfirst, { size: 21, color: INK, after: 220 }),
  body(author, { size: 19, color: MUTED, after: 60 }),
  body(date, { size: 19, color: MUTED, after: 60 }),
  new Paragraph({
    spacing: { before: 200, after: 220 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "D9D5CA" } },
    children: [],
  }),
);

for (const [tag, text] of blocks.slice(6)) {
  if (tag === 'b') {                       // spacer
    children.push(new Paragraph({ spacing: { after: 100 }, children: [] }));
  } else if (tag === 'h1') {
    children.push(new Paragraph({
      spacing: { before: 320, after: 140 },
      heading: HeadingLevel.HEADING_1,
      children: [new TextRun({ text, size: 28, bold: true, color: NAVY, font: "Calibri" })],
    }));
  } else if (tag === 'h2') {
    children.push(new Paragraph({
      spacing: { before: 240, after: 110 },
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun({ text, size: 23, bold: true, color: TEAL, font: "Calibri" })],
    }));
  } else if (tag === 'li') {
    children.push(new Paragraph({
      bullet: { level: 0 },
      spacing: { after: 90, line: 288 },
      children: [new TextRun({ text, size: 21, color: INK, font: "Calibri" })],
    }));
  } else if (text) {
    children.push(body(text));
  }
}

const doc = new Document({
  sections: [{
    properties: { page: { margin: { top: 1100, bottom: 1000, left: 1100, right: 1100 } } },
    children,
  }],
});

Packer.toBuffer(doc).then(b => {
  fs.writeFileSync('/home/claude/Phil_White_Paper.docx', b);
  console.log('written from', SOURCE, '-', blocks.length, 'blocks');
});
