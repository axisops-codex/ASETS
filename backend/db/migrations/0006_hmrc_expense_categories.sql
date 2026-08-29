-- =====================================================================
-- ASETS 0006 — expense categories that match HMRC's own boxes
--
-- The original ten categories were invented for a psychologist and then
-- mapped onto HMRC fields after the fact. That is backwards: the figures
-- end up on a Self Assessment submission, so the categories have to be
-- the ones HMRC actually recognises.
--
-- Two things the old list got wrong, both of which matter:
--
--   * There was nowhere to put a meal or a client dinner, so both landed
--     in "Other" -> otherExpenses, declaring as an allowable expense
--     something HMRC says plainly is not allowable
--     (gov.uk/expenses-if-youre-self-employed: "you cannot claim for
--     entertaining clients, suppliers and customers").
--
--   * Meals are allowable *only* on overnight business trips, which the
--     old list gave no way to express.
--
-- Entertainment is now its own category, flagged disallowable, and the
-- submission builder puts it in periodDisallowableExpenses as well as
-- periodExpenses — which is how HMRC expects a wholly disallowable cost
-- to be reported.
-- =====================================================================

SET search_path = asets, public;

ALTER TABLE asets.expense_categories
    ADD COLUMN IF NOT EXISTS disallowable boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS icon text NOT NULL DEFAULT 'pricetag-outline',
    ADD COLUMN IF NOT EXISTS hint text NOT NULL DEFAULT '';

-- New set. `code` is what the API returns and what expenses reference.
INSERT INTO asets.expense_categories (code, label, position, hmrc_field, disallowable, icon, hint) VALUES
 ('Office & admin',        'Office & admin',            1, 'adminCosts',                false, 'briefcase-outline',      'Stationery, postage, printing'),
 ('Phone & internet',      'Phone & internet',          2, 'adminCosts',                false, 'call-outline',           'The business share of your bills'),
 ('Software',              'Software',                  3, 'adminCosts',                false, 'laptop-outline',         'Subscriptions and licences'),
 ('Equipment',             'Equipment',                 4, 'otherExpenses',             false, 'hardware-chip-outline',  'Things you bought for the practice'),
 ('Travel',                'Travel',                    5, 'carVanTravelExpenses',      false, 'car-outline',            'Fuel, parking, train, bus, taxi'),
 ('Overnight trips',       'Overnight trips',           6, 'carVanTravelExpenses',      false, 'bed-outline',            'Hotels, and meals only on overnight trips'),
 ('Premises',              'Premises',                  7, 'premisesRunningCosts',      false, 'home-outline',           'Rent, rates, power, insurance'),
 ('Repairs',               'Repairs',                   8, 'maintenanceCosts',          false, 'construct-outline',      'Repairs and maintenance'),
 ('Supervision',           'Supervision',               9, 'professionalFees',          false, 'people-circle-outline',  'Clinical supervision'),
 ('Professional fees',     'Professional fees',        10, 'professionalFees',          false, 'ribbon-outline',         'Accountant, legal, indemnity, memberships'),
 ('Training / CPD',        'Training / CPD',           11, 'otherExpenses',             false, 'school-outline',         'Courses that maintain your skills'),
 ('Advertising',           'Advertising',              12, 'advertisingCosts',          false, 'megaphone-outline',      'Website, listings, directories'),
 ('Staff',                 'Staff',                    13, 'wagesAndStaffCosts',        false, 'person-add-outline',     'Salaries and subcontractors'),
 ('Bank charges',          'Bank charges',             14, 'financeCharges',            false, 'card-outline',           'Bank and card processing fees'),
 ('Client entertainment',  'Client entertainment',     15, 'businessEntertainmentCosts', true, 'wine-outline',           'HMRC does not allow this — recorded, but not deducted'),
 ('Other',                 'Other',                    16, 'otherExpenses',             false, 'pricetag-outline',       'Anything else wholly for the business')
ON CONFLICT (code) DO UPDATE SET
    label = EXCLUDED.label, position = EXCLUDED.position, hmrc_field = EXCLUDED.hmrc_field,
    disallowable = EXCLUDED.disallowable, icon = EXCLUDED.icon, hint = EXCLUDED.hint;

-- Move any existing expense off a code that is going away.
UPDATE asets.expenses SET category = 'Premises'          WHERE category = 'Office / Rent';
UPDATE asets.expenses SET category = 'Professional fees' WHERE category = 'Insurance';

DELETE FROM asets.expense_categories WHERE code IN ('Office / Rent', 'Insurance');
