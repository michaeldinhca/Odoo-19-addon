
// Owl slider
$(document).ready(function(){

// Date Picker
$('#filter-start').datepicker({
                    changeMonth : true,
                    changeYear : true,
                    showButtonPanel : true,
                    format : "mm/dd/yy",
                    dateFormat : 'yy-mm-dd',
                });

// Date Picker
$('#filter-end').datepicker({
                    changeMonth : true,
                    changeYear : true,
                    showButtonPanel : true,
                    format : "dd/mm/yy",
                    dateFormat : 'mm/dd/yy',
                });
                                
// Date Picker
$('#filter-to').datepicker({
                    changeMonth : true,
                    changeYear : true,
                    showButtonPanel : true,
                    format : "dd/mm/yy",
                    dateFormat : 'dd/mm/yy',
                });
$('#datetimepicker2').datetimepicker({
           locale: 'ru'
           //dateFormat : 'dd/mm/yy',
        });
 });

