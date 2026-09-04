/** @odoo-module **/
import { patch } from "@web/core/utils/patch";
import { SurveyForm } from "@survey/interactions/survey_form";

/**
 * The stock SurveyForm dispatches validation/submit-value-extraction per question type via
 * closed switch statements (see validateForm / prepareSubmitValues) - there's no extension
 * hook, so a new question type has to patch its way in rather than register a handler.
 * (Same approach as survey_file_upload's own patch, applied independently - patch() chains
 * cleanly across modules patching the same prototype methods.)
 */
patch(SurveyForm.prototype, {
    prepareSubmitValues(formData, params) {
        super.prepareSubmitValues(...arguments);
        for (const el of this.el.querySelectorAll(".o_survey_signature_value")) {
            params[el.name] = el.value;
        }
    },

    validateForm(formEl, formData) {
        const isValid = super.validateForm(...arguments);

        const errors = {};
        let signatureValid = true;
        for (const inputEl of formEl.querySelectorAll(".o_survey_signature_value")) {
            const questionWrapperEl = inputEl.closest(".js_question-wrapper");
            const questionId = questionWrapperEl.id;
            if (questionWrapperEl.hasAttribute("data-required") && !inputEl.value) {
                errors[questionId] = questionWrapperEl.dataset.constrErrorMsg || "";
                signatureValid = false;
            }
        }
        if (!signatureValid) {
            this.showErrors(errors);
        }
        return isValid && signatureValid;
    },
});
