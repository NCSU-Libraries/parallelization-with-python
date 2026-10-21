<div align="center">

<a href="https://www.lib.ncsu.edu/" aria-label="NC State University Libraries"><img src="site/images/lib_logo_whiteBG.svg" width="400" alt="NC State University Libraries logo" /></a>

<h2>Parallelization with Python</h2>

<a href="https://www.lib.ncsu.edu/workshops"><img alt="NC State Libraries Workshops" src="https://img.shields.io/badge/NC%20State%20Libraries-Workshops-red"></a>
<a href="https://www.lib.ncsu.edu/staff/department/data-science-services"><img alt="Data Science Services" src="https://img.shields.io/badge/Data%20Science%20Services-Libraries-red"></a>
<a href="https://go.ncsu.edu/getdatahelp"><img alt="Get Data Help" src="https://img.shields.io/badge/Get%20Data%20Help-go.ncsu.edu%2Fgetdatahelp-red"></a>

</div>

A 90-minute online workshop from NC State University Libraries' Data Science Services, part of Data Science Special
Topics. It shows how to use all of your computer's cores with Python's `multiprocessing`, taught through animations,
with hands-on work in Google Colab (nothing to install).

**Workshop site:** <https://ncsu-libraries.github.io/parallelization-with-python/>

## What's here

| Path | What it is |
| --- | --- |
| `site/` | The Quarto website and the slide deck (`site/slides/`) |
| `site/slides/anim/` | Standalone animation pages, embedded in the deck |
| `code/` | The forest-fire model that the demos use |
| `tools/` | A link checker, a screenshot script and the script that records the timings |

## Build it locally

You need [Quarto](https://quarto.org) 1.10 or later. RStudio ships one at
`/Applications/RStudio.app/Contents/Resources/app/quarto/bin/quarto`.

```bash
quarto render site            # builds site/_site, including the deck
quarto preview site           # or serve it locally while editing
python3 tools/check_links.py  # checks every link and image in site/_site
```

## Publishing

Pushing to `main` runs `.github/workflows/deploy-pages.yml`, which renders the site and deploys it to GitHub Pages. Set
**Settings → Pages → Source** to **GitHub Actions** *before* the first push. The first push of a root commit doesn't
trigger the paths-filtered workflow, so run it once from the **Actions** tab.

## License

Content is licensed [CC BY 4.0](LICENSE-CC-BY-4.0.md) and code is [MIT](LICENSE).
