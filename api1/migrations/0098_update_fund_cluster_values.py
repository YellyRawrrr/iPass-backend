from django.db import migrations


def forward_update_fund_cluster(apps, schema_editor):
    TravelOrder = apps.get_model('api1', 'TravelOrder')
    CertificateOfTravel = apps.get_model('api1', 'CertificateOfTravel')

    TravelOrder.objects.filter(fund_cluster='01_RF').update(fund_cluster='01-RF')
    TravelOrder.objects.filter(fund_cluster='07_TF').update(fund_cluster='07-TF')

    CertificateOfTravel.objects.filter(fund_cluster='01_RF').update(fund_cluster='01-RF')
    CertificateOfTravel.objects.filter(fund_cluster='07_TF').update(fund_cluster='07-TF')


def backward_update_fund_cluster(apps, schema_editor):
    TravelOrder = apps.get_model('api1', 'TravelOrder')
    CertificateOfTravel = apps.get_model('api1', 'CertificateOfTravel')

    TravelOrder.objects.filter(fund_cluster='01-RF').update(fund_cluster='01_RF')
    TravelOrder.objects.filter(fund_cluster='07-TF').update(fund_cluster='07_TF')

    CertificateOfTravel.objects.filter(fund_cluster='01-RF').update(fund_cluster='01_RF')
    CertificateOfTravel.objects.filter(fund_cluster='07-TF').update(fund_cluster='07_TF')


class Migration(migrations.Migration):

    dependencies = [
        ('api1', '0097_alter_certificateoftravel_fund_cluster_and_more'),
    ]

    operations = [
        migrations.RunPython(forward_update_fund_cluster, backward_update_fund_cluster),
    ]

