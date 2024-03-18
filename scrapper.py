import httpx
from bs4 import BeautifulSoup, ResultSet, PageElement, Tag
from ebooklib import epub
from dataclasses import dataclass
import datetime
import random

import asyncio
import time

"""
A key thing to note is that due to the presence of bonus chapters which are
out of sequence in the table of contents additional logic needs to be preformed.

Current logic flow is as follows:
1. Get links to all pages from table of contents
2. Asyncronousally process all links and generate a Chapter object for each
3. sort all chapters with a global index number
4. bind the epub


"""


@dataclass
class Chapter:
    """
    This is a data class representing an individual chapter
    I was planning on including better "Volume" and "Book" (as in meta-book) identification but it wasn't fully clear on how to accurately identify them.
    I may add this in a future update or if someone asks

    NOTE: Please pay attention to the global index as that actually sorts the chapters
    """

    url: str
    name: str
    data: str
    isBonus: bool
    isPrologue: bool
    isEpilogue: bool
    nextChapterUrl: str | None
    previousChapterUrl: str | None
    globalIndex: int | None  # hard indexing will be done by an additional logic flow


@dataclass
class Book:
    """
    This is an object that represents the actual "ebook"
    I had created this object to contain better indexing logic but I have not done that yet

    I am using the cover from Royal Road. I download a copy when its needed.
    """

    chapters: list[Chapter]
    title: str = "The Gods Are Bastards"
    author: str = "D. D. Webb"
    cover_url: str = (
        "https://www.royalroadcdn.com/public/covers-large/the-gods-are-bastards-aacauiaqzrm.jpg"
    )


def get_list_of_chapters(url: str) -> list[str]:
    urls: list[str] = []
    with httpx.Client() as client:
        response: httpx.Request = client.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    entryResults = soup.find("div", class_="entry-content")
    for child in entryResults.find_all(recursive=False):
        if child.name == "ul":
            for link in child.find_all("li"):
                url = link.find("a")["href"]
                urls.append(url)
    return urls


def chapter_parse(url: str, html: str) -> Chapter:
    """
    This function takes in the raw html received from scrapping the page and pulls the relevant data from it
    It returns a Chapter object
    """
    url = url
    name = ""
    data = ""
    isBonus = False
    isPrologue = False
    isEpilogue = False
    nextChapterUrl = None
    previousChapterUrl = None

    soup: Tag = BeautifulSoup(html, "html.parser")
    content: Tag = soup.find("div", class_="site-content")
    name = soup.find("h1", class_="entry-title").get_text()
    # Originally these booleans were going to be used for Volume and book indexing
    isBonus = "bonus" in name.lower()
    isPrologue = "prologue" in name.lower()
    isEpilogue = "epilogue" in name.lower()

    entry: Tag = content.find("div", class_="entry-content")
    ps: Tag = entry.find_all("p")
    if len(ps) == 0:
        raise IndexError
    for a in ps[0].find_all("a"):
        if "previous" in str(a).lower():
            previousChapterUrl = a["href"]
        if "next" in str(a).lower():
            nextChapterUrl = a["href"]
    data = ps[1 : len(ps) - 1]
    return Chapter(
        url=url,
        name=name,
        data=data,
        isBonus=isBonus,
        isPrologue=isPrologue,
        isEpilogue=isEpilogue,
        nextChapterUrl=nextChapterUrl,
        previousChapterUrl=previousChapterUrl,
        globalIndex=None,
    )


async def get_chapter(link: str, sem: asyncio.Semaphore) -> str:
    """
    This is a pretty naive approach to an async scraper with a semaphore limiter so not to overload the source site.
    There really isn't a need for an async scrapper as there are less than 1000 links and there is some form of rate limiting/ scrapper detection but a guy can dream...
    """
    retry = 3
    err = None
    while retry > 0:
        try:
            retry -= 1
            async with sem:
                async with httpx.AsyncClient() as aclient:
                    response: httpx.Response = await aclient.get(
                        link, follow_redirects=True
                    )
                    if response.status_code != 200:
                        raise httpx.HTTPStatusError(
                            f"Non-200 response: {response.status_code}",
                            response=response,
                            request=None,
                        )
                await asyncio.sleep(
                    random.randint(3, 5)
                )  # break up the async tasks a little
            print(f"processed - {link}")
            return chapter_parse(link, response.content)
        except Exception as e:
            err = e
            print((link + " " + str(e)))
            continue
    if retry <= 0 and err is not None:
        raise e


def generate_global_index(chapters: list[Chapter]) -> list[Chapter]:
    """
    This is a fun bit of logic that recursively searches an continuously shrinking list to correctly give each chapter a index
    This is needed because the bonus chapters are out of order in the ToC and I am grabbing the chapters asynchronously
    """

    def recursive_search(
        chapters_to_search: list[Chapter],
        target_chapter: Chapter = None,
        chapter_index=1,
        chapter_list=[],
    ):
        """
        takes in a list of chapters and then gets a seed chapter. From that seed chapter I try to find a the next chapter in the sequence with the "next chapter" url
        I then return a recursive function with the next chapter as a seed.
        """
        if target_chapter is None:
            for chapter in chapters_to_search:
                if chapter.isPrologue and chapter.previousChapterUrl is None:
                    target_chapter = chapter
                    chapters_to_search.remove(chapter)
                    break
        target_chapter.globalIndex = chapter_index
        chapter_list.append(target_chapter)
        chapter_index += 1
        if target_chapter.nextChapterUrl is None:
            return chapter_list
        next_chapter = None
        for chapter in chapters_to_search:
            if target_chapter.nextChapterUrl == chapter.url:
                next_chapter = chapter
                break
        if next_chapter is None:
            return chapter_list
        chapters_to_search.remove(next_chapter)
        return recursive_search(
            chapters_to_search=chapters_to_search,
            target_chapter=next_chapter,
            chapter_index=chapter_index,
            chapter_list=chapter_list,
        )

    return recursive_search(chapters_to_search=chapters)


def bind_ebook(book: Book):
    """
    This is a basic process to bind the epub. I think that I could do a better job with formatting but whatever...
    """
    ebook = epub.EpubBook()
    ebook.set_title(book.title)
    ebook.add_author(book.author)
    ebook.set_language("en")
    spine = []
    with open("tgab_cover.jpg", mode="wb") as file:
        cover = httpx.get(url=book.cover_url).content
        file.write(cover)
    ebook.set_cover(
        content="tgab_cover.jpg", file_name="tgab_cover.jpg", create_page=True
    )
    for chapter in sorted(book.chapters, key=lambda chapter: chapter.globalIndex):
        ebookChapter = epub.EpubHtml(
            title=chapter.name, file_name=str(chapter.globalIndex) + ".xhtml", lang="en"
        )
        chapter_text = ""
        for p in chapter.data:
            chapter_text += str(p)
        ebookChapter.content = f"<h2>{chapter.name}</h2><p>{str(chapter.globalIndex)}</p>{str(chapter_text)}"
        ebook.add_item(ebookChapter)
        spine.append(ebookChapter)
    ebook.spine = spine
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(item=epub.EpubNav())
    epub.write_epub(f"{book.title}.epub", ebook, {})


def binders_note(chapters: list[Chapter]):
    """This is just a link back to the sources and a data noting when this ebook was generated incase it is handed around and there are old versions"""
    chapterCount = len(chapters)
    d = datetime.datetime.now()
    note = f'<p>This ebook was auto-generated on {d:%B %d, %Y}</p><p>See the original work at: <a href="https://tiraas.net/">https://tiraas.net/<a/></p><p>See ebook generator at <a href="https://github.com/curohu/The-Gods-are-Bastards-Scrapper">https://github.com/curohu/The-Gods-are-Bastards-Scrapper</a></p>'
    end = Chapter(
        url="",
        name="Binder's Note",
        data=note,
        isBonus=False,
        isPrologue=False,
        isEpilogue=False,
        nextChapterUrl=None,
        previousChapterUrl=None,
        globalIndex=chapterCount + 2,
    )
    chapters.append(end)
    return chapters


def main():
    """Main function"""
    stime = time.time()
    tocUrl = "https://tiraas.net/table-of-contents/"
    chapterUrls: list[str] = get_list_of_chapters(tocUrl)
    print(f"Got {len(chapterUrls)} chapters to scrape")

    async def process_manager(urls):
        chapters = []
        # NOTE: limit active requests so not to be an a** and overload their site
        sem = asyncio.Semaphore(10)
        tasks = [asyncio.create_task(get_chapter(url, sem)) for url in urls]
        for task in tasks:
            chapters.append(await task)
        return chapters

    chapters: list[Chapter] = asyncio.run(process_manager(chapterUrls))
    print(f"generated {len(chapters)} chapters")
    chapters = generate_global_index(chapters)
    print("Reindexed all chapters")
    chapters = binders_note(chapters)
    print("Binding Book")
    book = Book(chapters)
    bind_ebook(book)
    print(f"{time.time()-stime:.2f}")


if __name__ == "__main__":
    print("Starting...")
    main()
