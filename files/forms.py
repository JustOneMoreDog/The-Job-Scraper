from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, FormField, SelectField, FieldList, SubmitField
from wtforms.validators import InputRequired, Length
import yaml


# Search Terms
class SearchTermsForm(FlaskForm):
    class SearchTermRow(FlaskForm):
        search_term_label = StringField(render_kw={'style': 'width: 50ch'})
    rows = FieldList(FormField(SearchTermRow), min_entries=3)
    confirm = SubmitField(label='Save')


# Minimum Jobs Per Search
class MinJobsForm(FlaskForm):
    class MinJobsRow(FlaskForm):
        min_jobs_label = StringField(render_kw={'style': 'width: 5ch'})
    rows = FieldList(FormField(MinJobsRow), min_entries=1, max_entries=1)


# Location Form
class LocationsForm(FlaskForm):
    class LocationRow(FlaskForm):
        location_label = StringField(render_kw={'style': 'width: 50ch'})
    rows = FieldList(FormField(LocationRow), min_entries=1)


# Experience Level Forms
class ExperienceLevelsForm(FlaskForm):
    class ExperienceRow(FlaskForm):
        experience_level_label = StringField(render_kw={'style': 'width: 10ch'})
    rows = FieldList(FormField(ExperienceRow), min_entries=5)


# Excluded Locations Forms
class ExcludedLocationsForm(FlaskForm):
    class LocationRow(FlaskForm):
        exclude_location_label = StringField(render_kw={'style': 'width: 50ch'})
    rows = FieldList(FormField(LocationRow), min_entries=1)


# Excluded Companies Forms
class ExcludedCompanies(FlaskForm):
    class CompanyRow(FlaskForm):
        excluded_org_label = StringField(render_kw={'style': 'width: 25ch'})
    rows = FieldList(FormField(CompanyRow), min_entries=1)


# Experience Level Forms
class WordWeightForm(FlaskForm):
    class KeywordRow(FlaskForm):
        keyword_label = StringField(render_kw={'style': 'width: 30ch'})
        weight_label = StringField(render_kw={'style': 'width: 10ch'})
    rows = FieldList(FormField(KeywordRow), min_entries=1)
