// n8n Code node: "Build Odoo lead"  (Mode: Run Once for Each Item, JavaScript)
// Turns the classifier's answer into the exact values Odoo needs for a new lead.

// Odoo ids: run `python odoo/show_ids.py` and replace these three lines with its output.
// Ids rarely change, so they are kept here as settings instead of looked up for every lead.
const TAG_IDS = { Buyer: 0, Distributor: 0, Importer: 0, Urgent: 0 };
const SOURCE_IDS = { web_form: 0, whatsapp: 0, email: 0, referral: 0 };
const SPAM_REASON_ID = 0;

// Fail loudly if any id was not filled in, instead of creating leads with missing data.
for (const [key, id] of Object.entries({ ...TAG_IDS, ...SOURCE_IDS, spam_reason: SPAM_REASON_ID })) {
  if (!id) throw new Error(`Odoo id for "${key}" is not set. Run odoo/show_ids.py.`);
}

const c = $json;                                   // the classifier's answer
const f = $('Extract enquiry fields').item.json;   // the original enquiry

// Odoo notes are HTML, so characters like < and > in a customer message must be escaped.
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const tagIds = [];
if (TAG_IDS[c.customer_type]) tagIds.push(TAG_IDS[c.customer_type]);
if (c.genuine && c.urgent) tagIds.push(TAG_IDS.Urgent);

const summary = c.genuine
  ? `Auto-sorted: ${c.customer_type} | ${c.vehicle} | ${c.quantity} vehicle(s) | AED ${c.budget_aed} | ${c.destination_country}${c.urgent ? ' | URGENT' : ''}`
  : 'Auto-sorted: not a genuine enquiry. Marked lost as spam.';

const vals = {
  type: 'lead',
  name: c.genuine ? `Enquiry - ${f.name} - ${c.vehicle}` : `Not genuine - ${f.name}`,
  contact_name: f.name,
  phone: f.phone,
  expected_revenue: c.budget_aed,
  description: `<p>${esc(f.message)}</p><p>${esc(summary)}</p>`,
  tag_ids: [[6, 0, tagIds]],
};

if (SOURCE_IDS[f.source]) vals.source_id = SOURCE_IDS[f.source];

// Spam is kept on record for reporting, but archived as lost so it never reaches the sales team.
if (!c.genuine) {
  vals.active = false;
  vals.probability = 0;
  vals.lost_reason_id = SPAM_REASON_ID;
}

return { json: { vals } };
