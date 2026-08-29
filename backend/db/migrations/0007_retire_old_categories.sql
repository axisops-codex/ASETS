-- =====================================================================
-- ASETS 0007 — retire the last of the pre-HMRC category codes
--
-- 0006 introduced "Phone & internet" but only retired two of the old
-- codes, leaving "Phone / Internet" behind as a duplicate that would
-- have shown up twice in the picker. Migrations are immutable once
-- applied, so the correction is a new one rather than an edit.
-- =====================================================================

SET search_path = asets, public;

UPDATE asets.expenses SET category = 'Phone & internet' WHERE category = 'Phone / Internet';
DELETE FROM asets.expense_categories WHERE code = 'Phone / Internet';

-- Guard against this class of mistake: every category must map to a
-- field the HMRC self-employment API actually accepts.
ALTER TABLE asets.expense_categories
    ADD CONSTRAINT expense_categories_known_hmrc_field CHECK (hmrc_field IN (
        'costOfGoods', 'paymentsToSubcontractors', 'wagesAndStaffCosts',
        'carVanTravelExpenses', 'premisesRunningCosts', 'maintenanceCosts',
        'adminCosts', 'businessEntertainmentCosts', 'advertisingCosts',
        'interestOnBankOtherLoans', 'financeCharges', 'irrecoverableDebts',
        'professionalFees', 'depreciation', 'otherExpenses'
    ));
