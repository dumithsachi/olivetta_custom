{
    'name': "Bdynamic PO Update",
    'version': '1.0',
    'summary': "Adds an action to update purchase orders via an external API.",
    'description': """
        This module overrides the standard Odoo purchase order functionality
        to include an action that updates an external system via a REST API call.
    """,
    'author': "Your Name",
    'website': "http://www.Bitzify.com",
    'category': 'Purchase',
    'depends': ['purchase'],
    'data': [
    ],
    'installable': True,
    'application': False,
    'license': 'AGPL-3',
}