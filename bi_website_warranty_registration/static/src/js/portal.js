/** @odoo-module **/


    $(document).ready(function (){
    
     if ($('.o_portal_details').length) {
        
        var country_id = $("select[name='country_id']")[0].dataset["count_id"];
        var state_id = $("select[name='state_id']")[0].dataset["stat_id"];
        
        if (country_id){
            $("select[name='country_id']").val(country_id);
        }

        if (state_id){
            $("select[name='state_id']").val(state_id);
        }

    }   
    