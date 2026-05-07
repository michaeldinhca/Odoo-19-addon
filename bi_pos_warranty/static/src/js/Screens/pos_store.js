/** @odoo-module */

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";
// import { EditListPopup } from "@point_of_sale/app/store/select_lot_popup/select_lot_popup";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { SelectLotPopup } from "@point_of_sale/app/components/popups/select_lot_popup/select_lot_popup";
import {
    makeAwaitable,
    ask,
}  from "@point_of_sale/app/utils/make_awaitable_dialog";
let extend_warranty;

patch(PosStore.prototype, {

	async processServerData() {
        await super.processServerData();
        this.extend_product_warranty = this.models['product.extended.warranty'].getAll();
    },

    async setup() {
        await super.setup(...arguments);
        this.set_lots_data(this.getOrder())
       
    },

     
    set_lots_data(order){
    	if (!order) {
            return false;
        }
		var self = this;
		// Temporary
		
		
		setInterval(function (){
			self.data.call("pos.order", "check_warranty_reg",[1]).then(function(output) {
				order.set_used_lots(output[0]);
				order.set_all_lots(output[1]);
			});
		},5000);
	},


	async editLots(product, packLotLinesToEdit) {

        let order = this.getOrder()
        var extended_warranty_period = [];
        var self = this;
        this.extend_product_warranty.forEach(function (notif) {
            for(var extend_id of product.extended_warranty_ids) {

                if (notif.id == extend_id.id){
                    extended_warranty_period.push(notif)
                }
            }

        });
        const isAllowOnlyOneLot = product.isAllowOnlyOneLot();
        let canCreateLots = this.pickingType.use_create_lots || !this.pickingType.use_existing_lots;


        let existingLots = [];
        try {
            existingLots = await this.data.call("pos.order.line", "get_existing_lots", [
                this.company.id,
                this.config.id,
                product.id,
            ]);
            if (!canCreateLots && (!existingLots || existingLots.length === 0)) {
                this.dialog.add(AlertDialog, {
                    title: _t("No existing serial/lot number"),
                    body: _t(
                        "There is no serial/lot number for the selected product, and their creation is not allowed from the Point of Sale app."
                    ),
                });
                return null;
            }
        } catch (ex) {
            logPosMessage("Store", "editLots", "Collecting existing lots failed", CONSOLE_COLOR, [
                ex,
            ]);
            const confirmed = await ask(this.dialog, {
                title: _t("Server communication problem"),
                body: _t(
                    "The existing serial/lot numbers could not be retrieved. \nContinue without checking the validity of serial/lot numbers ?"
                ),
                confirmLabel: _t("Yes"),
                cancelLabel: _t("No"),
            });
            if (!confirmed) {
                return null;
            }
            canCreateLots = true;
        }

       

        const existingLotsName = existingLots.map((l) => l.name);
        // if (!packLotLinesToEdit.length && existingLotsName.length === 1) {
        //     // If there's only one existing lot/serial number, automatically assign it to the order line
        //     return { newPackLotLines: [{ lot_name: existingLotsName[0] }] };
        // }
        const payload = await makeAwaitable(this.dialog, SelectLotPopup, {
            title: _t("Lot/Serial number(s) required for"),
            name: product.display_name,
            isSingleItem: isAllowOnlyOneLot,
            array: packLotLinesToEdit,
            options: existingLots,
            customInput: canCreateLots,
            uniqueValues: product.tracking === "serial",
            extended_warranty_period:extended_warranty_period
        });
        if (payload) {
            // Segregate the old and new packlot lines
            const modifiedPackLotLines = Object.fromEntries(
                payload.filter((item) => item.id).map((item) => [item.id, item.text])
            );
            const newPackLotLines = payload
                .filter((item) => !item.id)
                .map((item) => ({ lot_name: item.text }));

            let go_on = 0;
            self.set_lots_data();
            let orderline = order.selected_orderline;
            let used_lots_rec = order.get_used_lots();
            let all_lots_rec = order.get_all_lots();
            let count = 0;

            for (var line of newPackLotLines){
            
                count += 1
                let lot_name = line['lot_name'].toString();
                let x = used_lots_rec.indexOf(lot_name);
                let y = all_lots_rec.indexOf(lot_name);
                if (x == -1 && y >= 0){
                    go_on += 1;
                }
                if(x == -1 && y == -1 ){
                    self.dialog.add(AlertDialog, {
                        title: _t("Error: LOT Doesn't exists"),
                        body: _t("This lot is not exist, please enter valid lot.."),
                    });
                    return false
                }
                if(x >= 0){
                    self.dialog.add(AlertDialog, {
                        title: _t("Error: LOT already used"),
                        body: _t("This lot number is already used , please use another"),
                    });
                    return false
                }
            };

            if(go_on == count){
                return { modifiedPackLotLines, newPackLotLines };
            }else{
                return null;
            }
        } else {
            return null;
        }
    },
	

	async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        let merge = true;

        let order = this.getOrder();
        order.assertEditable();

        if (!order) {
            order = this.add_new_order();
        }

        const options = {
            ...opts,
        };

        if ("price_unit" in vals) {
            merge = false;
        }

        // const product = vals.product_id;

        // const values = {
        //     price_type: "price_unit" in vals ? "manual" : "original",
        //     price_extra: 0,
        //     price_unit: 0,
        //     order_id: this.getOrder(),
        //     qty: 1,
        //     tax_ids: product.taxes_id.map((tax) => ["link", tax]),
        //     ...vals,
        // };

        if (typeof vals.product_tmpl_id == "number") {
            vals.product_tmpl_id = this.data.models["product.template"].get(vals.product_tmpl_id);
        }
        const productTemplate = vals.product_tmpl_id;
        const values = {
            price_type: "price_unit" in vals ? "manual" : "original",
            price_extra: 0,
            price_unit: 0,
            order_id: this.getOrder(),
            qty: this.getOrder().preset_id?.is_return ? -1 : 1,
            tax_ids: productTemplate.taxes_id.map((tax) => ["link", tax]),
            product_id: productTemplate.product_variant_ids[0],
            ...vals,
        };

        // Handle refund constraints
        if (order.isSaleDisallowed(values, options)) {
            this.dialog.add(AlertDialog, {
                title: _t("Oops.."),
                body: _t("Ensure you validate the refund before taking another order."),
            });
            return;
        }

        // In case of configurable product a popup will be shown to the user
        // We assign the payload to the current values object.
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.isConfigurable() && configure) {
            const payload = await this.openConfigurator(values.product_id);

            if (payload) {
                const productFound = this.models["product.product"]
                    .filter((p) => p.raw?.product_template_variant_value_ids?.length > 0)
                    .find((p) =>
                        p.raw.product_template_variant_value_ids.every((v) =>
                            payload.attribute_value_ids.includes(v)
                        )
                    );

                Object.assign(values, {
                    attribute_value_ids: payload.attribute_value_ids
                        .filter((a) => {
                            if (productFound) {
                                const attr =
                                    this.data.models["product.template.attribute.value"].get(a);
                                return (
                                    attr.is_custom || attr.attribute_id.create_variant !== "always"
                                );
                            }
                            return true;
                        })
                        .map((id) => [
                            "link",
                            this.data.models["product.template.attribute.value"].get(id),
                        ]),
                    custom_attribute_value_ids: Object.entries(payload.attribute_custom_values).map(
                        ([id, cus]) => {
                            return [
                                "create",
                                {
                                    custom_product_template_attribute_value_id:
                                        this.data.models["product.template.attribute.value"].get(
                                            id
                                        ),
                                    custom_value: cus,
                                },
                            ];
                        }
                    ),
                    price_extra: values.price_extra + payload.price_extra,
                    qty: payload.qty || values.qty,
                    product_id: productFound || values.product_id,
                });
            } else {
                return;
            }
        } else if (values.product_id.product_template_variant_value_ids.length > 0) {
            // Verify price extra of variant products
            const priceExtra = values.product_id.product_template_variant_value_ids
                .filter((attr) => attr.attribute_id.create_variant !== "always")
                .reduce((acc, attr) => acc + attr.price_extra, 0);
            values.price_extra += priceExtra;
        }

        // In case of clicking a combo product a popup will be shown to the user
        // It will return the combo prices and the selected products
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.isCombo() && configure) {
            const payload = await makeAwaitable(this.dialog, ComboConfiguratorPopup, {
                product: values.product_id,
            });

            if (!payload) {
                return;
            }

            const comboPrices = computeComboItems(
                values.product_id,
                payload,
                order.pricelist_id,
                this.data.models["decimal.precision"].getAll(),
                this.data.models["product.template.attribute.value"].getAllBy("id")
            );

            values.combo_line_ids = comboPrices.map((comboItem) => [
                "create",
                {
                    product_id: comboItem.combo_item_id.product_id,
                    tax_ids: comboItem.combo_item_id.product_id.taxes_id.map((tax) => [
                        "link",
                        tax,
                    ]),
                    combo_item_id: comboItem.combo_item_id,
                    price_unit: comboItem.price_unit,
                    order_id: order,
                    qty: 1,
                    attribute_value_ids: comboItem.attribute_value_ids?.map((attr) => [
                        "link",
                        attr,
                    ]),
                    custom_attribute_value_ids: Object.entries(
                        comboItem.attribute_custom_values
                    ).map(([id, cus]) => {
                        return [
                            "create",
                            {
                                custom_product_template_attribute_value_id:
                                    this.data.models["product.template.attribute.value"].get(id),
                                custom_value: cus,
                            },
                        ];
                    }),
                },
            ]);
        }

        // In the case of a product with tracking enabled, we need to ask the user for the lot/serial number.
        // It will return an instance of pos.pack.operation.lot
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.isTracked() && configure) {
            const code = opts.code;
            let pack_lot_ids = {};
            const packLotLinesToEdit =
                (!values.product_id.isAllowOnlyOneLot() &&
                    this.getOrder()
                        .getOrderlines()
                        .filter((line) => !line.getDiscount())
                        .find((line) => line.product_id.id === values.product_id.id)
                        ?.getPackLotLinesToEdit()) ||
                [];

            // if the lot information exists in the barcode, we don't need to ask it from the user.
            if (code && code.type === "lot") {
                // consider the old and new packlot lines
                const modifiedPackLotLines = Object.fromEntries(
                    packLotLinesToEdit.filter((item) => item.id).map((item) => [item.id, item.text])
                );
                const newPackLotLines = [{ lot_name: code.code }];
                pack_lot_ids = { modifiedPackLotLines, newPackLotLines };
            } else {
                pack_lot_ids = await this.editLots(values.product_id, packLotLinesToEdit);
            }

            if (!pack_lot_ids) {
                return;
            } else {
                const packLotLine = pack_lot_ids.newPackLotLines;
                values.pack_lot_ids = packLotLine.map((lot) => ["create", lot]);
            }
        }

        // In case of clicking a product with tracking weight enabled a popup will be shown to the user
        // It will return the weight of the product as quantity
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.to_weight && this.config.iface_electronic_scale && configure) {
            if (values.product_id.isScaleAvailable) {
                this.isScaleScreenVisible = true;
                this.scaleData = {
                    productName: values.product_id?.display_name,
                    uomName: values.product_id.uom_id?.name,
                    uomRounding: values.product_id.uom_id?.rounding,
                    productPrice: this.getProductPrice(values.product_id),
                };
                const weight = await makeAwaitable(
                    this.env.services.dialog,
                    ScaleScreen,
                    this.scaleData
                );
                if (!weight) {
                    return;
                }
                values.qty = weight;
                this.isScaleScreenVisible = false;
                this.scaleWeight = 0;
                this.scaleTare = 0;
                this.totalPriceOnScale = 0;
            } else {
                await values.product_id._onScaleNotAvailable();
            }
        }

        // Handle price unit
        this.handlePriceUnit(values, order, vals.price_unit);

        const line = this.data.models["pos.order.line"].create({ ...values, order_id: order });
        line.setOptions(options);
        this.selectOrderLine(order, line);
        this.numberBuffer.reset();
        if (document.getElementById("extended_warranty_selector")){
        	extend_warranty = document.getElementById("extended_warranty_selector").value
        }

        const selectedOrderline = order.getSelectedOrderline();

        if (selectedOrderline){
			this.extend_product_warranty.forEach(function (notif) {
				if (notif.id == extend_warranty){
					var line_amount = 0;
					line_amount = notif.extended_warranty_amount
					selectedOrderline.setUnitPrice(line_amount)
					selectedOrderline.set_extend_warranty_line(notif.extended_warranty_period+" Year")
					selectedOrderline.price_type = "manual";

				}
			});
		}

        if (options.draftPackLotLines && configure) {
            selectedOrderline.setPackLotLines({
                ...options.draftPackLotLines,
                setQuantity: options.quantity === undefined,
            });
        }

        let to_merge_orderline;
        for (const curLine of order.lines) {
            if (curLine.id !== line.id) {
                if (curLine.canBeMergedWith(line) && merge !== false) {
                    to_merge_orderline = curLine;
                }
            }
        }

        if (to_merge_orderline) {
            to_merge_orderline.merge(line);
            line.delete();
            this.selectOrderLine(order, to_merge_orderline);
        } else if (!selectedOrderline) {
            this.selectOrderLine(order, order.get_last_orderline());
        }

        this.numberBuffer.reset();

        // FIXME: Put this in an effect so that we don't have to call it manually.
        order.recomputeOrderData();

        this.numberBuffer.reset();

        this.hasJustAddedProduct = true;
        clearTimeout(this.productReminderTimeout);
        this.productReminderTimeout = setTimeout(() => {
            this.hasJustAddedProduct = false;
        }, 3000);

        // FIXME: If merged with another line, this returned object is useless.
        return line;
    },

});