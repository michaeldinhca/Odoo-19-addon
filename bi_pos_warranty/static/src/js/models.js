import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
// import { EditListPopup } from "@point_of_sale/app/store/select_lot_popup/select_lot_popup";
import { Orderline } from "@point_of_sale/app/components/orderline/orderline";

patch(PosOrder.prototype, {
	setup() {
        super.setup(...arguments);
        this.used_lots = this.used_lots || [];
		this.all_lots = this.all_lots || [];        
    },

	set_all_lots(all_lots){
		this.all_lots = all_lots;
	},

	get_all_lots(){
		return this.all_lots;
	},

	set_used_lots(used_lots){
		this.used_lots = used_lots;
	},

	get_used_lots(){
		return this.used_lots;
	}
});


patch(PosOrderline.prototype, {

	setup(vals) {
        this.extended_warranty_line = this.extended_warranty_line|| "";
        return super.setup(...arguments);
    },
	
	set_extend_warranty_line(extended_warranty_line){
		this.extended_warranty_line = extended_warranty_line;
	},
	get_extend_warranty_line(){
		return this.extended_warranty_line;
	},
	
	
	export_for_printing() {
		var line = super.export_for_printing(...arguments);
		line.extended_warranty_line = this.get_extend_warranty_line();
		line.warranty_period = this.get_product().warranty_period;
		return line;
	},
	getDisplayData() {
		return {
		...super.getDisplayData(),

		extended_warranty_line: this.get_extend_warranty_line(),
		warranty_period: this.get_product().warranty_period,
			
		};
	},

});

// patch(Orderline, {
//     props: {
//         ...Orderline.props,
//         line: {
//             ...Orderline.props.line,
//             shape: {
//                 ...Orderline.props.line.shape,
//                 extended_warranty_line: { type: String, optional: true },
//                 warranty_period: { type: Number, optional: true },
//             },
//         },
//     },
// });


