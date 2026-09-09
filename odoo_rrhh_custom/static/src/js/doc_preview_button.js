/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

const IMAGE_EXTS = ["png", "jpg", "jpeg", "gif", "webp", "bmp"];

function mimetypeFromName(name) {
    const ext = (name || "").toLowerCase().split(".").pop();
    if (ext === "pdf") {
        return "application/pdf";
    }
    if (IMAGE_EXTS.includes(ext)) {
        return "image/" + ext.replace("jpg", "jpeg");
    }
    if (ext === "svg") {
        return "image/svg+xml";
    }
    return "application/octet-stream";
}

/** Modal que muestra el documento (PDF en iframe, imagen en img). */
export class DocPreviewDialog extends Component {
    static components = { Dialog };
    static template = "odoo_rrhh_custom.DocPreviewDialog";
    static props = {
        close: Function,
        name: { type: String },
        blob: { type: Blob },
        isPdf: { type: Boolean },
        isImage: { type: Boolean },
    };

    setup() {
        this.frameRef = useRef("frame");
        this.imgRef = useRef("img");
        // La URL del Blob se crea y se asigna al montar: crearla antes de que el
        // elemento exista deja el visor de PDF de Chrome en blanco.
        onMounted(() => {
            this.url = URL.createObjectURL(this.props.blob);
            const el = this.frameRef.el || this.imgRef.el;
            if (el) {
                el.src = this.url;
            }
        });
        onWillUnmount(() => {
            if (this.url) {
                URL.revokeObjectURL(this.url);
            }
        });
    }

    onDownload() {
        const url = URL.createObjectURL(this.props.blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = this.props.name || "documento";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
    }
}

/**
 * Botón "Previsualizar" para cualquier registro con campos 'attachment' +
 * 'attachment_filename' (líneas de documentación del candidato, permisos
 * laborales, etc.). Abre el archivo en un popup, sin necesidad de guardar: si
 * el binario está en memoria (recién subido) usa esos bytes; si el registro ya
 * está guardado los descarga de /web/content (usando record.resModel, así
 * sirve para cualquier modelo sin cambios). PDF e imágenes se ven en el modal;
 * el resto se descarga.
 */
export class DocPreviewButton extends Component {
    static template = "odoo_rrhh_custom.DocPreviewButton";
    static props = { "*": true };
    // Los atributos sueltos en <widget name="..." foo="1"/> no llegan como
    // props (Odoo solo reenvía los que el registro de widgets declara
    // explícitamente) — la variante compacta (solo ícono, sin texto, para
    // Permisos Laborales) se registra como una clase/entrada separada en vez
    // de depender de una prop custom.
    compact = false;

    setup() {
        this.notification = useService("notification");
        this.dialog = useService("dialog");
    }

    get record() {
        return this.props.record;
    }

    get hasFile() {
        return Boolean(this.record.data.attachment);
    }

    get _filename() {
        return this.record.data.attachment_filename || "documento";
    }

    async _buildBlob() {
        const type = mimetypeFromName(this._filename);
        const data = this.record.data.attachment;
        // Binario en memoria (recién subido, aún sin guardar).
        if (typeof data === "string" && data.length > 0) {
            try {
                const bin = atob(data);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) {
                    bytes[i] = bin.charCodeAt(i);
                }
                return new Blob([bytes], { type });
            } catch (e) {
                // cae al siguiente método
            }
        }
        // Línea ya guardada -> se descargan los bytes y se envuelven con el
        // MIME correcto (/web/content puede responder como octet-stream).
        if (this.record.resId) {
            const params = new URLSearchParams({
                model: this.record.resModel,
                id: this.record.resId,
                field: "attachment",
                filename_field: "attachment_filename",
                download: "true",
            });
            try {
                const res = await fetch(`/web/content?${params.toString()}`);
                if (res.ok) {
                    return new Blob([await res.arrayBuffer()], { type });
                }
            } catch (e) {
                // cae a null
            }
        }
        return null;
    }

    async onClick(ev) {
        ev.stopPropagation();
        const blob = await this._buildBlob();
        if (!blob) {
            this.notification.add(
                _t("No se pudo leer el archivo para previsualizar. Vuelve a subirlo."),
                { type: "warning" }
            );
            return;
        }
        const isPdf = blob.type === "application/pdf";
        const isImage = blob.type.startsWith("image/");

        if (!isPdf && !isImage) {
            // Sin visor para este tipo: descarga directa.
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = this._filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
            return;
        }

        this.dialog.add(DocPreviewDialog, {
            name: this._filename,
            blob,
            isPdf,
            isImage,
        });
    }
}

/** Misma lógica, solo ícono (sin texto) — para usarse junto a los íconos de
 * Editar/Limpiar del campo binario, en vez de en una lista con más espacio. */
export class DocPreviewButtonCompact extends DocPreviewButton {
    compact = true;
}

export const docPreviewButton = {
    component: DocPreviewButton,
};

export const docPreviewButtonCompact = {
    component: DocPreviewButtonCompact,
};

registry.category("view_widgets").add("doc_preview_button", docPreviewButton);
registry.category("view_widgets").add("doc_preview_button_compact", docPreviewButtonCompact);
