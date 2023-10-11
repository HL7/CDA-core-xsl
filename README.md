# CDA R2 Stylesheet
Quick Links: [Manual](#manual) - [Localization](#localization) - [Parameters](#parameters) - [Wiki](https://github.com/HL7/cda-core-xsl/wiki) - [Release Notes](https://github.com/HL7/cda-core-xsl/wiki/Revisions) - **[Security Notes](https://github.com/HL7/cda-core-xsl/wiki/Security-Notes)**

## Introduction
The CDA Release 2.0 publication comes with an *informative* stylesheet based on [XSLT 1.0](https://www.w3.org/TR/1999/REC-xslt-19991116). The stylesheet is maintained under responsibility of the [Structured Documents Workgroup](https://confluence.hl7.org/display/SD). Publications are under [releases](https://github.com/HL7/cda-core-xsl/releases)
The intent of the stylesheet is to offer an example of how to render a CDA document. It does this by rendering [XHTML 1.0 Strict](https://www.w3.org/TR/xhtml1/) with the following information:
- a summary of the header for the most important context, i.e. patient, author, encounter, documentationOf and inFulFillmentOf
- the section code, title and text (human readable text)
- the full header information
No CDA level 3, i.e. entry level information, is rendered.
## License
Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License. You may obtain a copy of the License at 
[http://www.apache.org/licenses/LICENSE-2.0](http://www.apache.org/licenses/LICENSE-2.0)
## Compatibility
The CDA XSL has been tested to work with Saxon-PE and major browsers. Effort has been put in to make rendering friendly for visually impaired people, based on the [American Foundation for the Blind Section 508](http://www.afb.org/info/programs-and-services/public-policy-center/technology-and-information-accessibility/section-508-key-links/1235). Effort has been put in to make the document friendly for screen and for print.
## Warranty
The CDA XSL is a sample rendering and should be used in that fashion without warranty or guarantees of suitability for a particular purpose. The stylesheet should be tested locally by implementers before production usage.
## Package Contents
The CDA R2 Stylesheet package contains at minimum two files that you need accessible for CDA documents to call or for programmatic access (see next section "*Manual*")
- CDA.xsl - main logic
- cda_l10n.xml - location file containing translations for terms (as of 4.0.0)
- cda_narrativeblock.xml - lookup file for checking if certain combinations of elements/attributes are legal in the narrative block (as of 4.0.2 beta 10)
## Manual
There are multiple ways to apply the stylesheet. If you have files on disk or on a webserver for a web browser to consume, you need a hint for the web browser how to render to document. This hint is called a processing instruction and needs to be inserted before the ClinicalDocument element:

```xml
 <?xml-stylesheet type="text/xsl" href="CDA.xsl"?>
```

or with an absolute path:

```xml
 <?xml-stylesheet type="text/xsl" href="http://example.org/cda/CDA.xsl"?>
```

The web browser needs to be able to access the relative or absolute location of the stylesheet. For security reasons, you probably want that location to be inside your own environment. 
Although the stylesheet supports many parameters, these are not configurable from a browser. If you need a different value for a stylesheet parameter than the default you can either update the default in the stylesheet, or run the stylesheet programmatically e.g. using Saxon-PE. If you update the defaults in the stylesheet, you might have a harder time updating the stylesheet if the base receives updates that you want in your environment too.
Running the stylesheet programmatically could be done in any environment that supports XSLT 1.0. The [major implementations of XSLT](https://en.wikipedia.org/wiki/XSLT) are Saxon, libxslt and Xalan. Example command line call for Saxon where the parameter for rendering the header is set to false could be:

```bash
java -jar ../lib/saxon-9/saxon9.jar -s:cda-example.xml -xsl:CDA.xsl -o:cda-example.html dohtmlheader=false mask-ids=2.16.840.1.113883.4.1
```

What this says:
- Run *java*, with the *saxon9.jar* file, to transform input file *cda-example.xml*, using stylesheet *CDA.xsl*, to output file *cda-example.html*, without rendering the header info, and mask any patient ID with root 2.16.840.1.113883.4.1 (US SSN)
## Localization
One of the core features of the updates to the stylesheet is localization or [l10n](https://acronyms.thefreedictionary.com/l10n). The original stylesheet has traditionally been US English, but the CDA is used all over the world and that means that applicability for other languages makes sense. The language is relevant in finding labels for things like "Patient ID" or "Date of birth", but also for structural attributes like classCode/typeCode/moodCode and NullFlavors. The language strings have been externalized into a separate xml file called cda-l10n.xml. The process works as follows:
- Determine language based on ClinicalDocument/languageCode/@code, unless override is done through parameter textLang -- expected format is 2 char language code from ISO639, followed by a hyphen and a 2 char country code from ISO3166, e.g. en-US. All will be lower-cased before use.
- For any label check if there is a translation element in cda-l10n.xml
  - check if requested language is available
  - check if match based on the first 2 character language code is available, e.g. en in en-US
  - check if match based on the value of parameter textLangDefault is available, normally en-US
  - check if match based on the first 2 character language code of parameter textLangDefault is available, e.g. en in en-US
  - Finally if all else fails, return key as label
### Adding support for a new language
Add a line like this in the languageList element at the top of the document:

```xml
 <language description="Dutch (Netherlands)" lang="nl-nl"/>
```

### Adding a new string to an existing translation element
Add new strings to existing translation elements as needed.
If the en-US term is sufficient for your language too: you do not need to list it in the language file. Add a line like this in the appropriate translation element:
 
```xml
 <value lang="nl-nl">Patiënt</value>
```

Note that the value for attribute lang needs to exist in the listing of languages at the top of the file.
### Adding a new translation element
This is only relevant when certain vocabulary or a certain identifier OID is inadvertently not supported. Other strings could only occur if you are updating the stylesheet itself. Add a translation element like this:

```xml
 <translation key="myKey">
   <comment>Label: my comment in free text</comment>
   <value lang="en-us">Patient</value>
   <value lang="nl-nl">Patiënt</value>
 </translation>
```

Make sure that you have en-US covered at the very least. Other languages as you see fit.
## Parameters
The stylesheet supports many ways to parametrize.
- `currentDate`
  - XSLT 1.0 does not have date function, so we need something to compare against e.g. to get someones age
  - Default: /hl7:ClinicalDocument/hl7:effectiveTime/@value
- `vocFile`
    - Vocabulary file containing language dependant strings such as labels
    - Default: cda_l10n.xml
- `textLangDefault`
  - Default language for retrieval of language dependant strings such as labels, e.g. 'en-US'. This is the fallback language in case the string is not available in the actual language. See also `textLang`.
  - Default: en-US
- `textLang`
  - Actual language for retrieval of language dependant strings such as labels, e.g. 'en-US'. Unless supplied, this is taken from the ClinicalDocument/language/@code attribute, or in case that is not present from `textlangDefault`.
  - Default /hl7:ClinicalDocument/hl7:languageCode/@code or if missing the value of $textlangDefault
- `textEncoding`
  - Currently unused. Unsupported by Internet Explorer. Text encoding to render the output in. Defaults to UTF-8 which is fine for most environments. Could change into more localized encodings such as cp-1252 (Windows Latin 1), iso-8859-1 (Latin 1), or shift-jis (Japanese Kanji table))
  - Default: utf-8
- `useJavascript`
  - Boolean value for whether the result document may contain JavaScript. Some environments forbid the use of JavaScript. Without JavaScript, certain more dynamic features may not work.
  - Default: true
- `externalCss`
  - Absolute or relative URI to an external Cascading Stylesheet (CSS) file that contains style attributes for custom markup, e.g. in the @styleCode attribute in Section.text
  - Default: none
- `font-family`
  - Determines the font family for the whole document unless overruled somewhere
  - Default: Verdana, Tahoma, sans-serif
- `font-size-main`
  - Determines the font size for all text unless otherwise specified, and is the base value for other font sizes
  - Default: 9pt
- `font-size-h1`
  - Determines the font size for text in the h1 tag
  - Defaults to font-size-main + 3
- `font-size-h2`
  - Determines the font size for text in the h2 tag
  - Defaults to font-size-main + 2
- `font-size-h3`
  - Determines the font size for text in the h3 tag
  - Defaults to font-size-main + 1
- `font-size-h4`
  - Determines the font size for text in the h4 tag
  - Defaults to font-size-main
- `font-size-h5`
  - Determines the font size for text in the h5 tag
  - Defaults to font-size-main
- `font-size-h6`
  - Determines the font size for text in the h6 tag
  - Defaults to font-size-main
- `font-size-footnote`
  - Determines the font size for text in footnotes
  - Defaults to font-size-main - 1
- `bgcolor-th`
  - Determines the background-color, as any legal hex, rgb or named color, for header like table elements, e.g. th tags
  - Defaults to "LightGrey"
- `bgcolor-td`
  - Determines the background-color, as any legal hex, rgb or named color, for body like table elements, e.g. td tags, defaults to "#f2f2f2".
  - Defaults to "#f2f2f2"
- `dohtmlheader`
  - Determines if the document title and top level summary of header information (patient/guardian/author/encounter/documentationOf, inFulfillmentOf) should be rendered. Defaults to "true", any other value is interpreted as "do not render". Some systems may have a context around the rendering of the document that would make rendering the header superfluous. Note that the footer, which may be switched off separately contains everything that the header does and more.
  - Default: true
- `dohtmlfooter`
  - Determines if the document footer containing a listing of everything in the CDA Header should be rendered. Defaults to "true", any other value is interpreted as "do not render". Some systems may have a context around the rendering of the document that would make rendering the footer superfluous, or just want to concentrate on document contents.
  - Default: true
- `menu-depth`
  - Determines depth of table of contents menu at the top of the document. Default is 1, which means just head section. Max is 3 which is head section + 2 levels (if any)
  - Default: 3
- `external-image-whitelist`
  - Security parameter. May contain a vertical bar separated list of URI prefixes, such as "http://www.example.com|https://www.example.com". See parameter `limit-external-images` for more detail.
  - Default: none
- `limit-external-images`
  - Security parameter. When set to 'yes' limits the URIs to images (if any) to locally attached images and/or images that are on the `external-image-whitelist`. When set to anything other than 'yes' also allows for arbritrary external images (e.g. through http:// or https://). Default value is 'yes' which is considered defensive against potential security risks that could stem from resources loaded from arbitrary source.
  - Default: yes
- `limit-pdf`
  - Security parameter. When set to 'yes' [sandboxes the iframe](https://html.spec.whatwg.org/multipage/origin.html#sandboxed-plugins-browsing-context-flag) for pdfs. Sandboxed iframe disallow plug-ins, including the plug-in needed to render pdf. Effectively this setting thus prohibits pdf rendering. When set to anything other than 'yes', pdf carrying iframes are not sandboxed and pdf rendering is possible. Default value is 'yes' which is considered defensive against potential security risks that could stem from resources loaded from arbitrary source.
  - Default: yes
- `mask-ids`
  - Privacy parameter. Accepts a comma separated list of patient ID root values (normally OID's). When a patient ID is encountered with a root value in this list, then the rendering of the extension will be xxx-xxx-xxx regardless of what the actual value is. This is useful to prevent public display of for example the US SSN. Default is to render any ID as it occurs in the document. Note that this setting only affects human rendering and that it does not affect automated processing of the underlying document. If the same value also occurs in the `skip-ids` list, then that takes precedence.
  - Default: none
- `skip-ids`
  - Privacy parameter. Accepts a comma separated list of patient ID root values (normally OID's). When a patient ID is encountered with a root value in this list, then the rendering of this ID will be skipped. This is useful to prevent public display of for example the US SSN. Default is to render any ID as it occurs in the document. Note that this setting only affects human rendering and that it does not affect automated processing of the underlying document.
  - Default: none
- `section-order`
  - Provides a list of top level section codes, comma separated, matching the section/code/@code attribute. If the list is empty, then default to document order. First in list, means first on screen. Any sections without a match are rendered in document order after the last matching section. If none of the top-level sections match, the order defaults to document order. Example: `42348-3,46240-8`
- `dosectionnumbering`
  - Determines if sections will receive numbering according to ClinicalDocument order. Value 'true' activates numbering. Top level sections are 1, 2, 3, 4, sub level sections are 1.1, 1.2, 1.2.1, 1.2.2 etc.
  - Default: false
## Acknowledgements
The stylesheet is the cumulative work of several developers; the most significant prior milestones were the foundation work from Lantana Group, HL7 Germany and Finland (Tyylitiedosto) and HL7 US (Calvin Beebe), and the presentation approach from Tony Schaller, medshare GmbH provided at IHIC 2009.
