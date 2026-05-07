# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.


{
    "name" : "Website Product Warranty Registration & Claim",
    "version" : "19.0.0.0",
    "category" : "Website",
    "depends" : ['portal','bi_warranty_registration','website','website_sale','account_payment',],
    "author": "BROWSEINFO",
    'summary': 'website product Warranty with serial number claim Warranty website renewal Warranty product website Warranty website Maintenance product service warranty website Maintenance service online warranty serial number Registration online service warranty request',
    "description": """
This Module allows to 
odoo register warranty Renew the warranty and Claim serial number Warranty Registration
odoo product claim serial number claim claim warranty renew warranty 
odoo Warranty serial number Registration Warranty renewal
       This module allow you 
odoo register warranty for a particular product Serial Number. There are two kind of warranty: 1. Free Warranty 2. Paid Warranty. With the help of this module you will be able to create and track warranty, Claim the already created warranties, Renew the warranties, Automatically invoice creation for a paid warranty, Automatically notification mail to the customer. 
    Help of this apps Warranty Registration and Tracking is easy
    Allow to configure two types of warranty : 1. Free Warranty 2. Paid Warranty
    Allow to configure different Warranty Teams Tags Claim Stages Renew Notification period
    Detailed Warranty and Claim History for better transperancy
    Unique Warranty per Product Serial No.
    Warranty Receipt Report
    automate warranty claims
    This Odoo Apps allow you register warranty for a particular product with its Serial Number. There are two kind of warranty: 1. Free Warranty 2. Paid Warranty. With the help of this odoo module you will be able to create and track warranty easily, using serial number start warranty period of your product with easy registration process. Warranty period and setup is configurable option under the product level and based on that warranty start date, end date and warranty period defines for each products.You can also Claim the already created warranties within warranty period and without warranty period with paid and free warranty setup. You can also have option Renew the warranty period of your product as per the configuration. Automatically invoice creation process is available for paid warranty and Automatically notification and reminders email to the customer from the Odoo system is also available. 
    If you want automatic warranty registration process at the time of sales order confirmation then its also possible with this Odoo apps you have to only install one small apps "Serial Number for Sales and invoice" to activate this feature, You can see the below section for more information. After activate this feature whenever you confirm sales order with product with serial number which has warranty configuration that's product's warranty registration is automatically added and warranty period is started for that product.

    odoo Warranty registration claim Warranty odoo registration claim Warranty odoo claim Warranty
    odoo warrenty registration product warrenty registration Warranty claim
    odoo Activate product Warranty odoo Warranty expired Warranty to be renew Warranty renewal
    odoo service warranty claim management odoo product service warranty claim management warranty invoice
    odoo Warranty product service warranty claim management warranty claim management
    odoo service claim management Warranty serial number
    


    Purpose :- 
This Module allows to 
    odoo register warranty from website Renew the warranty and Claim.
    odoo Website serial number Warranty Registration Website product claim Website serial number claim Website claim warranty Website renew warranty
    odoo Website Warranty serial number Registration from website Website Warranty renewal
    This module allow you register warranty for a particular product Serial Number from Website. There are two kind of warranty: 1. Free Warranty 2. Paid Warranty. With the help of this module you will be able to create and track warranty, Claim the already created warranties, Renew the warranties, Automatically invoice creation for a paid warranty, Automatically notification mail to the customer. 
    Help of this apps Warranty Registration and Tracking is easy
    odoo Allow to configure two types of warranty : 1. Free Warranty 2. Paid Warranty
    odoo Allow to configure different Warranty Teams, Tags, Claim Stages, Renew Notification period
    Detailed Warranty and Claim History for better transperancy
    odoo Unique Warranty per Product Serial No.
    odoo Website Warranty Receipt Report Website Activate the Warranty
    odoo Website Warranty expired Website Warranty to be renew Website Warranty renewal
    odoo Website warranty invoice odoo Website Warranty product odoo Website Warranty serial number

Warranty Receipt Report
    automate warranty claims
    
    warrenty registration
    product warrenty registration
    Warranty claim
     Activate the Warranty
    Warranty expired
    Warranty to be renew
    Warranty renewal
    service warranty
    claim management 
    product service warranty claim management
    warranty invoice
    Warranty product
    service warranty claim management
    warranty claim management
    service claim management
    Warranty serial number

    
    """,
    "website" : "https://www.browseinfo.com/demo-request?app=bi_website_warranty_registration&version=19&edition=Community",
    "price": 31,
    "currency": 'EUR',
    "data": [
        'data/data.xml',
        'views/warranty_reg_template.xml',
        
    ],
    'qweb': [
    ],
    
    
    'assets': {
        'point_of_sale.assets': [
            'bi_website_warranty_registration/static/src/css/profile_css.css',
            'bi_website_warranty_registration/static/src/js/custom.js',
            'bi_website_warranty_registration/static/src/js/portal.js',
        ],
    },
    
    
    
    "auto_install": False,
    "license":'OPL-1',
    "installable": True,
    "live_test_url" : "https://www.browseinfo.com/demo-request?app=bi_website_warranty_registration&version=19&edition=Community",
    "images":["static/description/Banner.gif"],
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
