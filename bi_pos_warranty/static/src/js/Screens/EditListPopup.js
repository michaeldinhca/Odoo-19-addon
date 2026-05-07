import { patch } from "@web/core/utils/patch";
// import { EditListPopup } from "@point_of_sale/app/store/select_lot_popup/select_lot_popup";
import { SelectLotPopup } from "@point_of_sale/app/components/popups/select_lot_popup/select_lot_popup";

// import { Navbar } from "@point_of_sale/app/navbar/navbar";

patch(SelectLotPopup, {
	defaultProps : {
        isLotNameUsed: () => false,
    },
    props: { ...SelectLotPopup.props,
    	extended_warranty_period: { type: Object },
	},
});
