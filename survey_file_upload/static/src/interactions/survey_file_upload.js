import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

export class SurveyFileUpload extends Interaction {
    static selector = ".o_survey_file_upload_widget";
    dynamicContent = {
        ".o_survey_file_upload_trigger": { "t-on-click": () => this.fileInputEl.click() },
        ".o_survey_file_upload_input": { "t-on-change": this.onFileInputChange },
        ".o_survey_file_upload_remove": { "t-on-click": this.onRemoveClick },
    };

    setup() {
        this.questionId = this.el.dataset.questionId;
        this.maxSizeMb = parseFloat(this.el.dataset.maxSizeMb) || 0;
        this.allowMultiple = this.el.dataset.multiple === "true";
        this.formEl = this.el.closest("form.o_survey-fill-form");
        this.valueInputEl = this.el.querySelector(".o_survey_file_upload_value");
        this.fileInputEl = this.el.querySelector(".o_survey_file_upload_input");
        this.triggerEl = this.el.querySelector(".o_survey_file_upload_trigger");
        this.listEl = this.el.querySelector(".o_survey_file_upload_list");
        this.errorEl = this.el.querySelector(".o_survey_file_upload_error");
        this.progressEl = this.el.querySelector(".o_survey_file_upload_progress");
        this.progressBarEl = this.el.querySelector(".o_survey_file_upload_progress_bar");
        this.progressPctEl = this.el.querySelector(".o_survey_file_upload_progress_pct");
    }

    _tokens() {
        return {
            surveyToken: this.formEl.dataset.surveyToken,
            answerToken: this.formEl.dataset.answerToken,
            csrfToken: this.formEl.querySelector('input[name="csrf_token"]').value,
        };
    }

    _currentIds() {
        return this.valueInputEl.value ? this.valueInputEl.value.split(",").filter(Boolean) : [];
    }

    async onFileInputChange(ev) {
        const files = Array.from(ev.target.files || []);
        ev.target.value = "";
        if (!files.length) {
            return;
        }
        this.errorEl.textContent = "";

        const existingCount = this._currentIds().length;
        if (!this.allowMultiple && existingCount + files.length > 1) {
            this.errorEl.textContent = _t("Only one file is allowed for this question.");
            return;
        }
        for (const file of files) {
            if (this.maxSizeMb && file.size > this.maxSizeMb * 1024 * 1024) {
                this.errorEl.textContent = _t('"%s" exceeds the %s MB limit.', file.name, this.maxSizeMb);
                return;
            }
        }

        const { surveyToken, answerToken, csrfToken } = this._tokens();
        const formData = new FormData();
        formData.append("csrf_token", csrfToken);
        for (const file of files) {
            formData.append("ufile", file);
        }

        this.triggerEl.disabled = true;
        this._setProgress(0);
        this.progressEl.classList.remove("d-none");
        try {
            const data = await this.waitFor(
                this._uploadWithProgress(
                    `/survey/file_upload/${surveyToken}/${answerToken}/${this.questionId}`,
                    formData,
                    (pct) => this._setProgress(pct)
                )
            );
            if (data.error) {
                this.errorEl.textContent = data.error;
            } else {
                if (data.errors && data.errors.length) {
                    this.errorEl.textContent = data.errors.join(" ");
                }
                for (const uploaded of data.files || []) {
                    this._addChip(uploaded);
                }
            }
        } catch {
            this.errorEl.textContent = _t("Upload failed. Please try again.");
        } finally {
            this.triggerEl.disabled = false;
            this.progressEl.classList.add("d-none");
        }
    }

    /**
     * fetch() has no upload-progress event - only XMLHttpRequest exposes
     * `upload.onprogress`, which is what lets the progress bar actually move
     * instead of just showing an indeterminate "uploading" state.
     */
    _uploadWithProgress(url, formData, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", url);
            xhr.upload.addEventListener("progress", (ev) => {
                if (ev.lengthComputable) {
                    onProgress(Math.round((ev.loaded / ev.total) * 100));
                }
            });
            xhr.addEventListener("load", () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        resolve(JSON.parse(xhr.responseText));
                    } catch (err) {
                        reject(err);
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}`));
                }
            });
            xhr.addEventListener("error", () => reject(new Error("network error")));
            xhr.addEventListener("abort", () => reject(new Error("aborted")));
            xhr.send(formData);
        });
    }

    _setProgress(pct) {
        this.progressBarEl.style.width = `${pct}%`;
        this.progressBarEl.setAttribute("aria-valuenow", pct);
        this.progressPctEl.textContent = `${pct}%`;
    }

    _addChip(uploaded) {
        const ids = this._currentIds();
        ids.push(String(uploaded.id));
        this.valueInputEl.value = ids.join(",");

        const itemEl = document.createElement("div");
        itemEl.className = "o_survey_file_upload_item d-flex align-items-center gap-2 mb-1";
        itemEl.dataset.attachmentId = uploaded.id;

        const iconEl = document.createElement("i");
        iconEl.className = "fa fa-file-o";
        const nameEl = document.createElement("span");
        nameEl.textContent = uploaded.name;
        const removeEl = document.createElement("button");
        removeEl.type = "button";
        removeEl.className = "btn btn-sm btn-link text-danger p-0 o_survey_file_upload_remove";
        removeEl.setAttribute("aria-label", _t("Remove file"));
        const removeIconEl = document.createElement("i");
        removeIconEl.className = "fa fa-times";
        removeEl.appendChild(removeIconEl);

        itemEl.append(iconEl, nameEl, removeEl);
        this.listEl.appendChild(itemEl);
    }

    async onRemoveClick(ev) {
        const itemEl = ev.target.closest(".o_survey_file_upload_item");
        const attachmentId = itemEl.dataset.attachmentId;
        const { surveyToken, answerToken, csrfToken } = this._tokens();
        const formData = new FormData();
        formData.append("csrf_token", csrfToken);

        try {
            const response = await this.waitFor(
                fetch(`/survey/file_upload/delete/${surveyToken}/${answerToken}/${attachmentId}`, {
                    method: "POST",
                    body: formData,
                })
            );
            const data = await this.waitFor(response.json());
            if (data.error) {
                this.errorEl.textContent = data.error;
                return;
            }
            const ids = this._currentIds().filter((id) => id !== String(attachmentId));
            this.valueInputEl.value = ids.join(",");
            itemEl.remove();
        } catch {
            this.errorEl.textContent = _t("Could not remove file. Please try again.");
        }
    }
}

registry.category("public.interactions").add("survey_file_upload.SurveyFileUpload", SurveyFileUpload);
