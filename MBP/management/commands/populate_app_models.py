from django.core.management.base import BaseCommand
from django.apps import apps
from django.utils.text import slugify
from MBP.models import AppModel

class Command(BaseCommand):
    help = 'Populate all models into AppModel table'

    def handle(self, *args, **kwargs):
        count = 0
        for model in apps.get_models():
            model_name = model.__name__
            app_label = model._meta.app_label
            verbose_name = model._meta.verbose_name.title()

            if not AppModel.objects.filter(name=model_name, app_label=app_label).exists():
                AppModel.objects.create(
                    name=model_name,
                    slug=slugify(model_name),
                    verbose_name=verbose_name,
                    app_label=app_label,
                    description=f"Auto-added model: {verbose_name}"
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f"Added {count} new AppModels."))
