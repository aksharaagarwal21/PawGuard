/**
 * Sources behind public health wording. Mirrors docs/CONTENT_REGISTER.md and docs/DATA_SOURCES.md; update all
 * three together. `reviewStatus` stays "unreviewed" until a qualified local reviewer approves the wording —
 * software authors (human or AI) cannot change it to approved.
 */
export type PublicSource = {
  id: string;
  title: string;
  publisher: string;
  url: string;
  usedFor: string;
  checked: string; // ISO date
  reviewStatus: "unreviewed" | "approved";
};

export const PUBLIC_SOURCES: PublicSource[] = [
  {
    id: "S01",
    title: "Rabies — fact sheet (updated 17 September 2026)",
    publisher: "World Health Organization",
    url: "https://www.who.int/news-room/fact-sheets/detail/rabies",
    usedFor: "Wound washing for at least 15 minutes; seeking medical attention; fatality once symptoms appear.",
    checked: "2026-10-05",
    reviewStatus: "unreviewed",
  },
  {
    id: "S02",
    title: "National Rabies Control Programme — Guidelines & Letters (Rabies Helpline 15400)",
    publisher: "National Centre for Disease Control, MoHFW, Government of India",
    url: "https://rabiesfreeindia.mohfw.gov.in/guidelines-letters",
    usedFor: "Helpline 15400 and the five states/UTs the programme lists it as serving.",
    checked: "2026-10-05",
    reviewStatus: "unreviewed",
  },
  {
    id: "S29",
    title: "Emergency Response Support System (Dial 112)",
    publisher: "Ministry of Home Affairs, Government of India",
    url: "https://112.gov.in/",
    usedFor: "112 as the national emergency number, integrated with health emergency services.",
    checked: "2026-10-05",
    reviewStatus: "unreviewed",
  },
  {
    id: "S30",
    title: "Frequently asked questions about rabies for the General Public (14 February 2018)",
    publisher: "World Health Organization",
    url: "https://www.who.int/docs/default-source/ntds/rabies/rabies-general-public-faqs.pdf",
    usedFor: "Bite mode: wash about 15 minutes with soap and water; go to a health facility as soon as possible; keep the biting animal under observation for 10 days; avoid irritants such as chili powder and plant juices.",
    checked: "2026-10-07",
    reviewStatus: "unreviewed",
  },
  {
    id: "S31",
    title: "National Action Plan for Dog Mediated Rabies Elimination from India by 2030",
    publisher: "National Centre for Disease Control, MoHFW, Government of India",
    url: "https://rabiesfreeindia.mohfw.gov.in/assets/Nrcp_img/NationalActiopPlan.pdf",
    usedFor: "Bite mode: wash the wound immediately with plenty of soap and water; consult a doctor immediately; do not apply chillies, mustard oil or other irritants (p. 131); signs within 10 days after exposure (p. 90).",
    checked: "2026-10-07",
    reviewStatus: "unreviewed",
  },
];
