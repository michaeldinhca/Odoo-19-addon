# -*- coding: utf-8 -*-
# Part of BrowseInfo. See LICENSE file for full copyright and licensing details.

{
    'name': 'Serial Number on Invoice and Sales With Scan feature',
    'version': '19.0.0.0',
    'category': 'sales',
    'summary': 'Scan Serial Number Via Barcode On invoice scan serial number on invoice scan serial number on sales scan lot via barcode scanner scan lot number in invoice add lot number via barcode scanner in sales serial number scan on invoice scan invoice via barcode',
    'description' :"""
        Serial number on sales order line, Serial number on invoice line, lot number on sales order line, lot number on invoice line,
        Scan product by barcode, add product by barcode scan, add product on sale order, add barcode on sale order, scan barcode on sale order, sale order barcode scan, sale order product scan , product scan on sale order, Serial number scan on sale order, lot number add on sale order, lot number scan on sale order, Serial number product scan, add product on invoice by scan,add serial number on invoice by scan, scan lot number on scan by barocode, add barcode on invoice, scan barcode on invoice,invoice barcode scan, invoice product scan , product scan on invoice, Serial number scan on invoice, lot number add on invoice, lot number scan on invoice, Serial number product scan, Scan serial number on invoice, scan product on sale order, scan barcode on invoice.
    all in one barcode scanner

        Sales, Purchase, Invoice- All In One Barcode Scanner
        add product on sales order by barcode
        add product on purchase order by barcode
        add prooduct on invoice by barcode
        Add Product on Sales,Purchase and Invoice using barcode scanner
Numéro de série sur la ligne de commande client, numéro de série sur la ligne de facture, numéro de lot sur la ligne de commande client, numéro de lot sur la ligne de facture, Scannez le produit par code-barres, ajoutez le produit par scan code-barres, ajoutez le produit sur la commande, ajoutez le code-barres sur la commande, scannez le code-barres sur la commande, scannez le code-barres, scannez le produit, scannez le numéro de série ordre, numéro de lot ajouter à la commande, numéro de lot numériser sur la commande, numéro de série numériser produit, ajouter produit sur facture par scan, ajouter numéro de série sur facture par scan, numériser numéro de lot scanné par barocode, ajouter code à barres sur facture, scan code à barres sur la facture, scan du code barres, facture produit, scan produit sur la facture, scan du numéro de série sur la facture, numéro de lot ajouté sur la facture, numérisation du numéro de lot sur la facture, numérisation du numéro de série, numérisation du produit commande, scan code à barres sur facture.

Número de serie en la línea de orden de venta, Número de serie en la línea de factura, Número de lote en la línea de orden de venta, Número de lote en la línea de factura,
         Escanee el producto por código de barras, agregue producto por escaneo de código de barras, agregue producto en orden de venta, agregue código de barras en orden de venta, escanee código de barras en orden de venta, escaneo de código de barras de orden de venta, escaneo de producto de orden de venta, escaneo de producto en orden de venta, escaneo de número de serie a la venta orden, número de lote agregar en orden de venta, número de lote escanear en orden de venta, escaneo de producto de número de serie, agregar producto en factura por escaneo, agregar número de serie en factura por escaneo, escanear número de lote en escanear por barocode, agregar código de barras en la factura, escanear código de barras en factura, escaneo de código de barras de factura, escaneo de producto de factura, escaneo de producto en factura, escaneo de número de serie en factura, número de lote añadir en factura, escaneo de número de lote en factura, escaneo de producto de número de serie, número de serie de escaneo en factura, escanear producto a la venta orden, escanee el código de barras en la factura.
    """,
    'author': 'BROWSEINFO',
    'website': 'https://www.browseinfo.com',
    "price": 39,
    "currency": 'EUR',
    'depends': ['sale_management','account','stock'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/sale_order_scan_views.xml',
        'views/sale_view.xml',
        'views/invoice_view.xml',
        'views/stock_view.xml',
    ],
    'license': 'OPL-1',
    'website': "https://www.browseinfo.com/demo-request?app=v9_sale_invoice_serial&version=19&edition=Community",
    'live_test_url': 'https://www.browseinfo.com/demo-request?app=v9_sale_invoice_serial&version=19&edition=Community',
    'installable': True,
    'auto_install': False,
   "images":['static/description/Banner.gif'],
}
