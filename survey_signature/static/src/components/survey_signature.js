/** @odoo-module **/
import { Component, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { NameAndSignature } from "@web/core/signature/name_and_signature";

/**
 * Thin wrapper around Odoo's own core `NameAndSignature` widget - the exact
 * "Auto / Draw / Load" signature pad used to sign a quotation or invoice on
 * the customer portal (see `portal.SignatureForm`) - adapted to write its
 * result into a hidden input instead of RPC-ing its own submit endpoint, so
 * it plugs into the survey form's normal Next/Submit flow like any other
 * question's answer input.
 */
export class SurveySignature extends Component {
    static template = "survey_signature.SurveySignature";
    static components = { NameAndSignature };
    static props = {
        questionId: { type: [Number, String] },
        defaultName: { type: String, optional: true },
        defaultImage: { type: String, optional: true },
    };
    static defaultProps = {
        defaultName: "",
        defaultImage: "",
    };

    setup() {
        this.valueInputRef = useRef("valueInput");
        this.signature = useState({
            name: this.props.defaultName,
            signatureImage: this.props.defaultImage || undefined,
            getSignatureImage: () => "",
            resetSignature: () => {},
            isSignatureEmpty: !this.props.defaultImage,
        });
        this.nameAndSignatureProps = {
            signature: this.signature,
            fontColor: "black",
            onSignatureChange: () => this.onSignatureChange(),
        };
        if (this.props.defaultImage) {
            // sync immediately so a prefilled-but-untouched signature still submits
            this._writeValue(this.props.defaultName, this.props.defaultImage);
        }
    }

    onSignatureChange() {
        const image = this.signature.isSignatureEmpty ? "" : this.signature.getSignatureImage();
        this._writeValue(this.signature.name, image);
    }

    _writeValue(name, image) {
        if (this.valueInputRef.el) {
            this.valueInputRef.el.value = image ? JSON.stringify({ name, image }) : "";
        }
    }
}

registry.category("public_components").add("survey_signature.signature_widget", SurveySignature);
